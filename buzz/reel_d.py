"""정치 계정 릴스/쇼츠 D 디자인 (1080x1920, 30fps).

장면: 훅(사진 위 큰 질문) → 본문 줄마다(사진 꽉 채움 또는 피드 카드) → 한마디(계정 색 전면) → 팔로우.
- 목소리: edge-tts(무료). 단어별 시간을 받아 자막을 말하는 순간에 맞춰 강조(가라오케식).
- 그림은 PIL로 한 장씩 그려 ffmpeg로 바로 인코딩.

build(content, cards_dir, out_mp4, work) — content 는 content.json(+ reel{hook,lines}, channel)
"""
import asyncio
import json
import math
import os
import shutil
import subprocess
import sys
import wave

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

sys.path.insert(0, os.path.dirname(__file__))
import poster_d as P  # noqa: E402

W, H, FPS = 1080, 1920, 30
VOICE = os.getenv("REEL_VOICE", "ko-KR-HyunsuMultilingualNeural")


def _ffmpeg():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg       # PC에 ffmpeg가 없으면 pip 패키지에 들어 있는 것 사용
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


FF = _ffmpeg()


# ---------- 목소리 ----------
def _ssl_patch():
    ca = os.getenv("EDGE_TTS_CA")
    if ca:
        import ssl
        import edge_tts.communicate as cm
        cm._SSL_CTX = ssl.create_default_context(cafile=ca)


ENGINE = os.getenv("REEL_TTS", "supertonic")      # supertonic(기본, 더 사람 같은 목소리) / edge
ST_VOICE = os.getenv("REEL_ST_VOICE", "M2")
_ST = None


def _supertonic():
    global _ST
    if _ST is None:
        try:
            import supertonic
        except ImportError:   # 처음 한 번 자동 설치(무료, 모델 약 300MB는 첫 실행 때 내려받음)
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "supertonic"], check=False)
            import supertonic
        t = supertonic.TTS(auto_download=True)
        _ST = (t, t.get_voice_style(voice_name=ST_VOICE))
    return _ST


def _tts_supertonic(text, mp3, rate):
    import numpy as np
    t, style = _supertonic()
    pct = float(str(rate).replace("%", "") or 0)
    wav, _ = t.synthesize(text, voice_style=style, lang="ko", total_steps=10, speed=1.08 * (1 + pct / 100),
                          silence_duration=0.15)
    a = np.asarray(wav, dtype=np.float32).reshape(-1)
    sr = t.sample_rate
    raw = mp3[:-4] + "_st.wav"
    t.save_audio(wav, raw)
    out = mp3[:-4] + ".wav"
    subprocess.run([FF, "-y", "-loglevel", "error", "-i", raw, "-ar", "44100", "-ac", "1", out], check=True)
    dur = len(a) / sr
    # 단어별 시간(엔진이 안 주므로 글자 수 비율로 나눔): 앞뒤 무음 제외
    loud = np.where(np.abs(a) > 0.02)[0]
    s0, s1 = (loud[0] / sr, loud[-1] / sr) if len(loud) else (0.0, dur)
    toks = text.split()
    wts = [max(1, sum(ch.isalnum() for ch in w)) + (1.5 if w[-1:] in ".?!," else 0) for w in toks]
    tot, acc, words = sum(wts), 0.0, []
    for w, k in zip(toks, wts):
        a0 = s0 + (s1 - s0) * acc / tot
        acc += k
        words.append((a0, s0 + (s1 - s0) * acc / tot, w))
    return dur, words, out


def tts(text, mp3, rate="+8%"):
    """반환: (길이초, [(시작, 끝, 단어)])"""
    if ENGINE == "supertonic":
        try:
            return _tts_supertonic(text, mp3, rate)
        except Exception as e:
            print("supertonic 목소리 실패 → edge-tts로:", e)
    words = []
    try:
        import edge_tts
        _ssl_patch()

        async def go():
            com = edge_tts.Communicate(text, VOICE, rate=rate, boundary="WordBoundary")
            with open(mp3, "wb") as f:
                async for ch in com.stream():
                    if ch["type"] == "audio":
                        f.write(ch["data"])
                    elif ch["type"] == "WordBoundary":
                        s = ch["offset"] / 1e7
                        words.append((s, s + ch["duration"] / 1e7, ch["text"]))
        asyncio.run(go())
        wav = mp3[:-4] + ".wav"
        subprocess.run([FF, "-y", "-loglevel", "error", "-i", mp3, "-ar", "44100", "-ac", "1", wav], check=True)
        with wave.open(wav) as w:
            dur = w.getnframes() / w.getframerate()
        return dur, _align(text, words), wav
    except Exception as e:  # 인터넷이 안 되면 무음 + 글자수로 시간 배분
        print("tts 실패 → 무음:", e)
        toks = text.split()
        dur = max(1.6, len(text.replace(" ", "")) * 0.13)
        step = dur / max(1, len(toks))
        wav = mp3[:-4] + ".wav"
        _silence(wav, dur)
        return dur, [(i * step, (i + 1) * step, t) for i, t in enumerate(toks)], wav


def _align(text, words):
    """음성 엔진 단어(문장부호 빠짐)를 원문 띄어쓰기 단위에 맞춘다."""
    toks = text.split()
    if not words:
        return []
    out, wi = [], 0
    for t in toks:
        core = "".join(ch for ch in t if ch.isalnum())
        if wi >= len(words):
            last = out[-1][1] if out else 0
            out.append((last, last + 0.2, t))
            continue
        s, e, _ = words[wi]
        acc = "".join(ch for ch in words[wi][2] if ch.isalnum())
        wi += 1
        while core and len(acc) < len(core) and wi < len(words):
            acc += "".join(ch for ch in words[wi][2] if ch.isalnum())
            e = words[wi][1]
            wi += 1
        out.append((s, e, t))
    return out


def _silence(path, secs):
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(44100)
        w.writeframes(b"\x00\x00" * int(44100 * secs))


# ---------- 그림 도구 ----------
def cover_fit(im, size, cy=0.4):
    return ImageOps.fit(im, size, Image.LANCZOS, centering=(0.5, cy))


def ease(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def stroke_text(d, xy, text, f, fill, sw=6, sc=(0, 0, 0)):
    d.text(xy, text, font=f, fill=fill, stroke_width=sw, stroke_fill=sc)


class Scene:
    def __init__(self, kind, dur, words=None, **kw):
        self.kind, self.dur, self.words, self.kw = kind, dur, words or [], kw


def chunks(words, max_chars=20, max_words=6):
    out, cur = [], []
    for i, w in enumerate(words):
        n = sum(len(x[2]) for x in cur) + len(w[2])
        if cur and (n > max_chars or len(cur) >= max_words):
            out.append(cur); cur = []
        cur.append(w)
        rest = sum(len(x[2]) for x in words[i + 1:])
        if w[2][-1:] in ".?!" and rest > 4 and sum(len(x[2]) for x in cur) >= 6:
            out.append(cur); cur = []
    if len(out) and cur and sum(len(x[2]) for x in cur) <= 7 and \
            sum(len(x[2]) for x in out[-1]) + sum(len(x[2]) for x in cur) <= max_chars + 6:
        out[-1] += cur; cur = []
    if cur:
        out.append(cur)
    return out


# ---------- 장면 그리기 ----------
class Renderer:
    def __init__(self, content, cards_dir):
        self.c = content
        P.set_channel(content.get("channel", "right"))
        self.C = P.C
        cards = content["cards"]
        self.cover = cards[0]
        self.kicker = P.clean(self.cover.get("kicker", ""))
        self.date = P._date_label(content)
        self.card_imgs = sorted(f for f in os.listdir(cards_dir) if f.endswith(".jpg")) if cards_dir else []
        self.cards_dir = cards_dir
        self.photos = [c["photo"] for c in cards if c.get("photo") and os.path.exists(c["photo"]["path"])]
        self.cache = {}

    def photo_base(self, ph, size):
        key = (ph["path"], size)
        if key not in self.cache:
            im = Image.open(ph["path"]).convert("RGB")
            im = cover_fit(im, size, ph.get("cy", 0.4))
            self.cache[key] = ImageEnhance.Contrast(im).enhance(1.06)
        return self.cache[key]

    def kenburns(self, ph, size, t, zin=True, pan=0.0):
        bw, bh = int(size[0] * 1.14), int(size[1] * 1.14)
        base = self.photo_base(ph, (bw, bh))
        z = 1.04 + 0.10 * (t if zin else 1 - t)
        cw, ch = size[0] * 1.14 / z, size[1] * 1.14 / z
        cx = bw / 2 + pan * (bw - cw) / 2 * (t - 0.5) * 2
        cy = bh / 2
        cx = min(max(cx, cw / 2), bw - cw / 2)
        box = (cx - cw / 2, max(0, cy - ch / 2), cx + cw / 2, min(bh, cy + ch / 2))
        return base.resize(size, Image.BILINEAR, box=box)

    # 공통 위층: 진행 막대 + 브랜드
    def chrome(self, d, prog, dark=True):
        d.rectangle((0, 0, W, 10), fill=(40, 40, 46))
        d.rectangle((0, 0, int(W * prog), 10), fill=self.C["accent"] if dark else self.C["ink"])
        P.spaced(d, (64, 96), self.C["brand"], P.PX(28), (255, 255, 255), 6)

    def captions(self, d, words, t, y=1360):
        groups = chunks(words)
        cur = None
        for g in groups:
            if g[0][0] - 0.05 <= t:
                cur = g
        if not cur:
            return
        f = P.PX(74)
        text_w = [d.textlength(w[2], font=f) for w in cur]
        sp = d.textlength(" ", font=f)
        # 두 줄까지 나눔
        lines, line, lw = [], [], 0
        for w, tw in zip(cur, text_w):
            if line and lw + tw > W - 160:
                lines.append(line); line, lw = [], 0
            line.append((w, tw)); lw += tw + sp
        lines.append(line)
        rise = (1 - ease((t - cur[0][0]) / 0.15)) * 28
        yy = y + rise
        for ln in lines:
            total = sum(tw for _, tw in ln) + sp * (len(ln) - 1)
            x = (W - total) / 2
            for (s, e, wtxt), tw in ln:
                active = s - 0.03 <= t < e + 0.08
                if active:
                    d.rounded_rectangle((x - 12, yy - 4, x + tw + 12, yy + 96), 14, fill=self.C["accent"])
                    stroke_text(d, (x, yy + 4), wtxt, f, (255, 255, 255), 0)
                else:
                    stroke_text(d, (x, yy + 4), wtxt, f, (255, 255, 255) if s <= t else (230, 230, 236), 7)
                x += tw + sp
            yy += 112

    def frame_hook(self, sc, t, prog):
        ph = self.photos[0] if self.photos else None
        if ph:
            img = self.kenburns(ph, (W, H), t / sc.dur, True, 0.3)
            img = ImageEnhance.Brightness(img).enhance(0.62)
        else:
            img = Image.new("RGB", (W, H), self.C["deep"])
        layer, mask = P.fade((W, H), 0.35, 0.95, self.C["ink"])
        img.paste(layer, (0, 0), mask)
        d = ImageDraw.Draw(img)
        self.chrome(d, prog)
        P.pill(d, (64, 160), self.date, P.PX(32), self.C["accent"], (255, 255, 255), pad=(20, 10), r=8)
        d.text((64, 640), self.kicker, font=P.PX(42), fill=self.C["mark"])
        # 질문을 단어별로 등장
        size = 132
        text = " ".join(w[2] for w in sc.words)
        while size > 80 and len(P.bwrap(d, text, size, W - 128)) > 3:
            size -= 6
        lines = P.bwrap(d, text, size, W - 128)
        shown = len(sc.words)          # 첫 1초에 멈추게: 처음부터 질문 전체를 크게
        k, y = 0, 720
        for li, ln in enumerate(lines):
            x = 64
            parts = ln.split()
            if li == len(lines) - 1:
                tw = P.blen(d, ln, size)
                vis = min(1.0, max(0.0, (shown - k) / max(1, len(parts))))
                if vis > 0:
                    d.rectangle((50, y + size * 0.1, 50 + (tw + 28) * ease(vis), y + size * 1.08),
                                fill=self.C["accent"])
            for p in parts:
                if k < shown:
                    x = P.btext(d, (x, y), p + " ", size, (255, 255, 255))
                else:
                    x += P.blen(d, p + " ", size)
                k += 1
            y += int(size * 1.15)
        # 표지 제목을 작게
        tl = self.cover.get("title") or []
        tl = " ".join(tl) if isinstance(tl, list) else tl
        d.text((64, y + 40), P.clean(tl), font=P.PB(40), fill=(220, 220, 228))
        if ph:
            cr = ph.get("credit", "")
            d.text((64, H - 300), cr, font=P.PM(22), fill=(170, 170, 178))
        return img

    def frame_line(self, sc, t, prog):
        u = t / sc.dur
        mode = sc.kw.get("mode")
        img = Image.new("RGB", (W, H), self.C["ink"])
        if mode == "photo":
            ph = sc.kw["photo"]
            p = self.kenburns(ph, (W, 1520), u, sc.kw.get("zin", True), sc.kw.get("pan", 0.4))
            layer, mask = P.fade((W, 1520), 0.55, 0.97, self.C["ink"])
            p.paste(layer, (0, 0), mask)
            l2, m2 = P.fade((W, 260), 0, 1, (0, 0, 0), 170, 0)
            p.paste(l2, (0, 0), m2)
            img.paste(p, (0, 0))
            d = ImageDraw.Draw(img)
            cr = ph.get("credit", "")
            d.text((W - 64 - d.textlength(cr, font=P.PM(22)), 210), cr, font=P.PM(22), fill=(200, 200, 208))
        else:
            card = Image.open(os.path.join(self.cards_dir, sc.kw["card"])).convert("RGB")
            # 흐린 배경 + 카드
            bg = cover_fit(card, (W // 4, H // 4)).filter(ImageFilter.GaussianBlur(8)).resize((W, H))
            bg = ImageEnhance.Brightness(bg).enhance(0.35)
            img.paste(bg)
            s = 0.84 + 0.04 * ease(u)
            cw, chh = int(1080 * s), int(1350 * s)
            cimg = card.resize((cw, chh), Image.BILINEAR)
            x, y = (W - cw) // 2, 190 + int((1 - ease(min(1, u * 4))) * 60)
            sh = Image.new("L", (cw + 60, chh + 60), 0)
            ImageDraw.Draw(sh).rounded_rectangle((30, 30, cw + 30, chh + 30), 30, fill=150)
            sh = sh.filter(ImageFilter.GaussianBlur(18))
            img.paste((0, 0, 0), (x - 30, y - 10), sh)
            m = Image.new("L", (cw, chh), 0)
            ImageDraw.Draw(m).rounded_rectangle((0, 0, cw - 1, chh - 1), 26, fill=255)
            img.paste(cimg, (x, y), m)
            d = ImageDraw.Draw(img)
            # 자막 자리 어둡게
            layer, mask = P.fade((W, 700), 0.0, 0.5, self.C["ink"], 0, 235)
            img.paste(layer, (0, H - 700), mask)
            d = ImageDraw.Draw(img)
        self.chrome(d, prog)
        P.pill(d, (64, 150), self.kicker, P.PX(30), (0, 0, 0), (255, 255, 255), pad=(18, 9), r=8)
        self.captions(d, sc.words, t)
        return img

    def frame_punch(self, sc, t, prog):
        img = Image.new("RGB", (W, H), self.C["accent"])
        d = ImageDraw.Draw(img)
        d.text((40, 160), "“", font=P.BH(560), fill=self.C["deep"])
        self.chrome(d, prog, dark=False)
        a = ease(t / 0.25)
        P.pill(d, (64 - int((1 - a) * 300), 560), self.C["label"], P.PX(46), self.C["ink"], (255, 255, 255),
               pad=(28, 14), r=10)
        words = sc.words[sc.kw.get("skip", 0):]
        text = " ".join(w[2] for w in words)
        size = 118
        while size > 70 and len(P.bwrap(d, text, size, W - 128)) > 5:
            size -= 6
        lines = P.bwrap(d, text, size, W - 128)
        shown = sum(1 for w in words if w[0] - 0.05 <= t)
        k, y = 0, 720
        for ln in lines:
            x = 64
            for p in ln.split():
                if k < shown:
                    x = P.btext(d, (x, y), p + " ", size, (255, 255, 255))
                k += 1
            y += int(size * 1.18)
        d.text((64, y + 50), "생각 다른 친구한테 보내 보세요", font=P.PX(46), fill=self.C["ink"])
        d.text((64, y + 120), "이 계정의 의견이에요. 여러분 생각은 댓글로!", font=P.PB(34), fill=(255, 235, 230))
        return img

    def frame_end(self, sc, t, prog):
        img = Image.new("RGB", (W, H), self.C["ink"])
        d = ImageDraw.Draw(img)
        self.chrome(d, prog)
        a = ease(t / 0.3)
        y = 700 + int((1 - a) * 60)
        d.text((64, y), "하루 5번", font=P.PX(56), fill=(255, 255, 255))
        P.btext(d, (64, y + 90), "정치 이슈, 짧고 세게", 96, (255, 255, 255))
        d.rectangle((64, y + 240, 64 + P.blen(d, self.C["handle"], 92) + 30, y + 360), fill=self.C["accent"])
        P.btext(d, (80, y + 250), self.C["handle"], 92, (255, 255, 255))
        d.text((64, y + 420), "팔로우하고 피드에서 카드로 자세히 보기", font=P.PB(40), fill=(200, 200, 210))
        d.text((64, H - 330), "※ 언론 보도를 AI가 정리했어요. 한마디는 이 계정의 의견이에요.", font=P.PM(26),
               fill=(140, 140, 150))
        return img

    def draw(self, sc, t, prog):
        return getattr(self, "frame_" + sc.kind)(sc, t, prog)


# ---------- 조립 ----------
def plan(content, R, work):
    reel = content.get("reel") or {}
    out = []
    os.makedirs(work, exist_ok=True)
    hook = P.clean(reel.get("hook") or "")
    if hook:
        dur, words, wav = tts(hook, os.path.join(work, "a00.mp3"), "+4%")
        out.append((Scene("hook", dur + 0.5, words), wav))
    lines = [P.clean(x) for x in reel.get("lines") or []]
    mids = R.card_imgs[1:-2] if len(R.card_imgs) > 3 else R.card_imgs
    ph_i = 0
    for i, ln in enumerate(lines):
        dur, words, wav = tts(ln, os.path.join(work, f"a{i + 1:02d}.mp3"))
        if i % 2 == 0 and R.photos:
            ph = R.photos[(ph_i + 1) % len(R.photos)] if len(R.photos) > 1 else R.photos[0]
            ph_i += 1
            kw = dict(mode="photo", photo=ph, zin=(i // 2) % 2 == 0, pan=0.5 if i % 4 == 0 else -0.5)
        elif mids:
            kw = dict(mode="card", card=mids[min(len(mids) - 1, int(i * len(mids) / max(1, len(lines))))])
        else:
            kw = dict(mode="photo", photo=R.photos[0]) if R.photos else dict(mode="card", card=R.card_imgs[0])
        out.append((Scene("line", dur + 0.3, words, **kw), wav))
    outro = content["cards"][-1]
    punch = P.clean(outro.get("punch") or "")
    if punch:
        lab = R.C["label"]
        dur, words, wav = tts(f"{lab}. {punch}", os.path.join(work, "a90.mp3"), "+6%")
        skip = len(lab.split())
        out.append((Scene("punch", dur + 1.0, words, skip=skip), wav))
    end_wav = os.path.join(work, "a99.wav")
    _silence(end_wav, 2.2)
    out.append((Scene("end", 2.2), end_wav))
    return out


def build(content, cards_dir, out_mp4, work):
    R = Renderer(content, cards_dir)
    scenes = plan(content, R, work)
    # 오디오: 장면 길이에 맞춰 자르고/늘려 이어붙임
    parts = []
    for i, (sc, wav) in enumerate(scenes):
        p = os.path.join(work, f"seg{i:02d}.wav")
        subprocess.run([FF, "-y", "-loglevel", "error", "-i", wav, "-af", f"apad=whole_dur={sc.dur:.3f}",
                        "-t", f"{sc.dur:.3f}", "-ar", "44100", "-ac", "1", p], check=True)
        parts.append(p)
    lst = os.path.join(work, "list.txt")
    open(lst, "w").write("".join(f"file '{os.path.abspath(p)}'\n" for p in parts))
    audio = os.path.join(work, "voice.wav")
    subprocess.run([FF, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", audio],
                   check=True)
    total = sum(sc.dur for sc, _ in scenes)
    enc = subprocess.Popen([FF, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", audio,
                            "-af", "loudnorm=I=-15:TP=-1.5", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-shortest",
                            "-movflags", "+faststart", out_mp4], stdin=subprocess.PIPE)
    t0, prev = 0.0, None
    XF = 0.2
    for sc, _ in scenes:
        n = int(round(sc.dur * FPS))
        for k in range(n):
            t = k / FPS
            fr = R.draw(sc, t, (t0 + t) / total)
            if prev is not None and t < XF:   # 장면 전환: 짧게 겹치며 넘어감
                fr = Image.blend(prev, fr, ease(t / XF))
            enc.stdin.write(fr.tobytes())
            last = fr
        prev = last
        t0 += sc.dur
    enc.stdin.close()
    enc.wait()
    if enc.returncode:
        raise RuntimeError("ffmpeg 실패")
    return out_mp4


def cover_frame(content, cards_dir, out_jpg, work):
    """쇼츠 썸네일용: 훅 장면 마지막 모습"""
    R = Renderer(content, cards_dir)
    hook = P.clean((content.get("reel") or {}).get("hook") or "")
    words = [(0, 0, w) for w in hook.split()]
    R.draw(Scene("hook", 1.0, words), 0.99, 0.02).save(out_jpg, quality=90)
    return out_jpg


if __name__ == "__main__":
    post, out = sys.argv[1], sys.argv[2]
    c = json.load(open(os.path.join(post, "content.json"), encoding="utf-8"))
    cd = sys.argv[3] if len(sys.argv) > 3 else post
    print(build(c, cd, out, os.path.join(os.path.dirname(os.path.abspath(out)) or ".", "_reelwork")))
