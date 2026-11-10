"""릴스 영상 v2 (1080x1920, 9:16)

레이어 구조 (장면마다)
  ① 배경: 사진 + 어둡게 그라데이션 → 천천히 확대/축소 (배경만 움직임)
  ② 고정 UI: 번호·분류·출처·사진 저작자 (PNG 오버레이)
  ③ 애니메이션 글자(ASS 자막): 제목 팝업 → 목소리에 맞춰 한 구절씩 뜨고 단어가 색으로 채워지는 자막
장면 사이: 슬라이드 전환 / 화면 맨 위: 진행 바 / reels_bgm.mp3 있으면 배경음악

내레이션: bot/tts.py (타입캐스트 → 무료 음성 → 무음 자막 순서로 자동 선택)
"""
import os
import re
import shutil
import subprocess
from datetime import datetime

from PIL import Image, ImageDraw

from bot import render as R
from bot.tts import synth

RW, RH, FPS = 1080, 1920, 30
XF = 0.35                                   # 장면 전환 길이(초)
SAFE_TOP, SAFE_BOTTOM, SAFE_RIGHT = 230, 1540, 960
FONT_DIR = R.FONT_DIR
TITLE_FONT = "Black Han Sans"


# ── 공통 유틸 ──────────────────────────────────────────────────
def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg 실패: {' '.join(cmd[:6])}...\n{r.stderr[-1500:]}")


def _dur(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", path], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def _ass_color(rgb, alpha=0):
    r, g, b = rgb
    return f"&H{alpha:02X}{b:02X}{g:02X}{r:02X}"


def _ts(t):
    t = max(0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _esc(t):
    return t.replace("\\", "").replace("{", "(").replace("}", ")")


# ── 배경 이미지 ────────────────────────────────────────────────
def _bg_image(photo, path):
    img = Image.new("RGB", (RW, RH), R.BG)
    kind = photo[2] if photo else "scene"
    if photo:
        ph = Image.open(photo[0]).convert("RGB")
        sc = max(RW / ph.width, RH / ph.height)
        ph = ph.resize((int(ph.width * sc) + 1, int(ph.height * sc) + 1), Image.LANCZOS)
        x = (ph.width - RW) // 2
        y = int((ph.height - RH) * (0.12 if kind == "person" else 0.4))
        img.paste(ph.crop((x, y, x + RW, y + RH)), (0, 0))
    grad = Image.new("L", (1, RH))
    for i in range(RH):
        t = i / RH
        if kind in ("person", "event"):
            a = 80 if t < 0.08 else 15 if t < 0.36 else int(15 + 200 * min(1, (t - 0.36) / 0.18))
        else:
            a = int(140 + 80 * t)
        grad.putpixel((0, i), min(a, 222 if photo else 255))
    img.paste(Image.new("RGB", (RW, RH), R.BG), (0, 0), grad.resize((RW, RH)))
    img.save(path, quality=95)
    return kind


# ── 고정 UI 오버레이 ───────────────────────────────────────────
def _overlay(path, photo=None, num=None, tag=None, person=None, sources=None, extra=None):
    ov = Image.new("RGBA", (RW, RH), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    d.rectangle([0, 0, RW, 14], fill=(0, 0, 0, 120))                  # 진행 바 트랙
    if photo and photo[1]:
        f = R.font(22, "regular")
        d.text((RW - 30 - d.textlength(photo[1], font=f), 112), photo[1], font=f,
               fill=(225, 225, 230, 255), stroke_width=1, stroke_fill=(0, 0, 0, 255))
    if num is not None:
        nf = R.font(150, "title")
        d.text((70, SAFE_TOP - 20), f"{num:02d}", font=nf, fill=R.ACCENT + (255,),
               stroke_width=4, stroke_fill=(0, 0, 0, 255))
        tf = R.font(40, "bold")
        tx = int(70 + d.textlength(f"{num:02d}", font=nf) + 30)
        tw = d.textlength(tag or "정치", font=tf)
        d.rounded_rectangle([tx, SAFE_TOP + 48, tx + tw + 48, SAFE_TOP + 116], radius=34,
                            fill=(0, 0, 0, 200), outline=(255, 255, 255, 255), width=3)
        d.text((tx + 24, SAFE_TOP + 53), tag or "정치", font=tf, fill=(255, 255, 255, 255))
    if person:
        d.text((70, person[1]), person[0], font=R.font(44, "bold"), fill=(255, 255, 255, 255),
               stroke_width=4, stroke_fill=(0, 0, 0, 255))
    if sources:
        d.text((70, SAFE_BOTTOM - 10), "출처: " + ", ".join(sources[:4]), font=R.font(30, "regular"),
               fill=(210, 210, 216, 255), stroke_width=2, stroke_fill=(0, 0, 0, 255))
    d.text((70, SAFE_BOTTOM + 40), R.ACCOUNT, font=R.font(32, "bold"), fill=(255, 255, 255, 200),
           stroke_width=2, stroke_fill=(0, 0, 0, 255))
    if extra:
        extra(d)
    ov.save(path)


# ── 자막(ASS) ─────────────────────────────────────────────────
def _ass_header():
    hi = _ass_color(R.YELLOW)
    white = _ass_color((255, 255, 255))
    black = _ass_color((0, 0, 0))
    shadow = _ass_color((0, 0, 0), 80)
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {RW}
PlayResY: {RH}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Title,{TITLE_FONT},100,{hi},{hi},{black},{shadow},0,0,0,0,100,100,0,0,1,7,5,7,0,0,0,1
Style: Hook,{TITLE_FONT},132,{hi},{hi},{black},{shadow},0,0,0,0,100,100,0,0,1,9,6,7,0,0,0,1
Style: Cap,{TITLE_FONT},92,{hi},{white},{black},{shadow},0,0,0,0,100,100,0,0,1,8,5,5,0,0,0,1
Style: Big,{TITLE_FONT},118,{white},{white},{black},{shadow},0,0,0,0,100,100,0,0,1,9,6,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _wrap_lines(text, size, width, max_lines):
    img = Image.new("RGB", (10, 10))
    d = ImageDraw.Draw(img)
    return R.wrap(d, text, R.font(size, "title"), width)[:max_lines]


def _pop_block(lines, x, y, size, start, end, style="Title", line_gap=1.18, color=None):
    """여러 줄 제목: 줄마다 0.12초 간격으로 튀어나오는 효과."""
    ev = []
    for i, ln in enumerate(lines):
        t0 = start + i * 0.12
        c = f"\\1c{_ass_color(color)}" if color else ""
        tag = (f"{{\\pos({x},{int(y + i * size * line_gap)})\\fs{size}\\fad(120,0)\\fscx72\\fscy72{c}"
               f"\\t(0,180,\\fscx106\\fscy106)\\t(180,280,\\fscx100\\fscy100)}}")
        ev.append(f"Dialogue: 1,{_ts(t0)},{_ts(end)},{style},,0,0,0,,{tag}{_esc(ln)}")
    return ev


def _chunks(words, max_chars=11, max_words=3):
    """단어들을 화면에 한 번에 보여줄 짧은 구절로 묶기."""
    out, cur = [], []
    for w in words:
        cur.append(w)
        txt = " ".join(x["text"] for x in cur)
        if (len(txt.replace(" ", "")) >= max_chars or len(cur) >= max_words
                or re.search(r"[.?!,…]$", w["text"])):
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


def _captions(words, offset, scene_end, y=1290):
    """목소리 타이밍에 맞춘 구절 자막 + 단어가 차례로 노란색으로 채워지는 효과(\\kf)."""
    ev = []
    groups = _chunks(words)
    for gi, g in enumerate(groups):
        st = offset + g[0]["start"]
        en = offset + (groups[gi + 1][0]["start"] if gi + 1 < len(groups) else g[-1]["end"] + 0.35)
        en = min(max(en, st + 0.35), scene_end)
        parts, t = [], g[0]["start"]
        for w in g:
            k = max(1, int(round((w["end"] - t) * 100)))
            parts.append(f"{{\\kf{k}}}{_esc(w['text'])} ")
            t = w["end"]
        tag = f"{{\\pos({RW // 2},{y})\\fad(60,40)\\fscx88\\fscy88\\t(0,90,\\fscx100\\fscy100)}}"
        ev.append(f"Dialogue: 2,{_ts(st)},{_ts(en)},Cap,,0,0,0,,{tag}{''.join(parts).strip()}")
    return ev


# ── 장면 렌더 ─────────────────────────────────────────────────
def _scene(work, k, photo, overlay_kw, ass_events, audio, dur, zoom_in=True):
    bg = os.path.join(work, f"bg{k}.jpg")
    _bg_image(photo, bg)
    ov = os.path.join(work, f"ov{k}.png")
    _overlay(ov, photo, **overlay_kw)
    ass = os.path.join(work, f"s{k}.ass")
    with open(ass, "w", encoding="utf-8") as f:
        f.write(_ass_header() + "\n".join(ass_events) + "\n")
    z0, z1 = (1.0, 1.09) if zoom_in else (1.09, 1.0)
    scale = (f"scale=w='trunc({RW}*({z0}+({z1}-{z0})*t/{dur:.3f})/2)*2':h=-2:eval=frame:flags=bicubic,"
             f"crop={RW}:{RH},setsar=1")
    out = os.path.join(work, f"seg{k}.mp4")
    ass_arg = ass.replace("\\", "/").replace(":", "\\:")
    fc = (f"[0:v]{scale}[b];[b][1:v]overlay=0:0[o];"
          f"[o]subtitles=filename='{ass_arg}':fontsdir='{FONT_DIR}',format=yuv420p[v];"
          f"[2:a]aresample=44100,apad,atrim=0:{dur:.3f}[a]")
    _run(["ffmpeg", "-y", "-loglevel", "error",
          "-loop", "1", "-framerate", str(FPS), "-t", f"{dur:.3f}", "-i", bg,
          "-loop", "1", "-framerate", str(FPS), "-t", f"{dur:.3f}", "-i", ov,
          "-i", audio, "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
          "-t", f"{dur:.3f}", "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
          "-c:a", "aac", "-b:a", "160k", "-ac", "2", out])
    return out


def _join_audio(parts, gap, out):
    """여러 음성 파일을 gap초 간격으로 이어 붙이기 → (경로, 각 조각 시작 시각)."""
    starts, t, inputs, flt = [], 0.0, [], []
    for i, (p, d) in enumerate(parts):
        starts.append(t)
        inputs += ["-i", p]
        flt.append(f"[{i}:a]aresample=44100,aformat=channel_layouts=stereo,apad=pad_dur={gap}[a{i}]")
        t += d + gap
    flt.append("".join(f"[a{i}]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=0:a=1[out]")
    _run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(flt),
          "-map", "[out]", "-c:a", "pcm_s16le", out])
    return out, starts, t


def build_reel(content, channel_id, out_dir, pick) -> str:
    work = os.path.join(out_dir, "_reel")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)
    stories = content["stories"]
    segs = []

    # ── 인트로 ──
    hook = content.get("reel_hook") or content["cover_title"]
    a, w, d = synth(hook, os.path.join(work, "n_intro"), channel_id, "toneup")
    dur = max(3.2, d + 0.7)
    now = datetime.now(R.KST)
    hook_lines = _wrap_lines(R.title_text(hook), 132, SAFE_RIGHT - 70, 3)

    def intro_extra(dd):
        dd.text((70, SAFE_TOP), f"{now:%Y.%m.%d} ({'월화수목금토일'[now.weekday()]})",
                font=R.font(44, "bold"), fill=(255, 255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0, 255))
        lab_f = R.font(50, "title")
        lw = dd.textlength(R.LABEL, font=lab_f)
        dd.rectangle([70, SAFE_TOP + 80, 70 + lw + 44, SAFE_TOP + 170], fill=R.ACCENT + (255,))
        dd.text((92, SAFE_TOP + 92), R.LABEL, font=lab_f, fill=(255, 255, 255, 255))
        y = 1080
        for i, s in enumerate(stories, 1):
            t = R.wrap(dd, s["headline"], R.font(44, "bold"), SAFE_RIGHT - 160)[0]
            dd.text((70, y), f"{i:02d}", font=R.font(44, "bold"), fill=R.ACCENT + (255,),
                    stroke_width=2, stroke_fill=(0, 0, 0, 255))
            dd.text((150, y), t, font=R.font(44, "bold"), fill=(255, 255, 255, 255),
                    stroke_width=2, stroke_fill=(0, 0, 0, 255))
            y += 68
    ev = _pop_block(hook_lines, 70, 640, 132, 0.15, dur, style="Hook")
    segs.append((_scene(work, 0, pick(content.get("cover_person"), stories[0].get("tag"), 11,
                                     stories[0].get("photo_queries")),
                        {"extra": intro_extra}, ev, a, dur, True), dur))

    # ── 이슈 장면 ──
    for i, s in enumerate(stories, 1):
        photo = pick(s.get("person"), s.get("tag"), 20 + i, s.get("photo_queries"))
        person_layout = bool(photo) and photo[2] in ("person", "event")
        head = s["headline"]
        cm = s.get("reel_comment") or s.get("comment") or ""
        a1, w1, d1 = synth(f"{i}번. {head}", os.path.join(work, f"n{i}a"), channel_id, "toneup")
        a2, w2, d2 = synth(cm, os.path.join(work, f"n{i}b"), channel_id, "angry")
        audio, starts, total = _join_audio([(a1, d1), (a2, d2)], 0.25, os.path.join(work, f"n{i}.wav"))
        dur = total + 0.5
        ty = 900 if person_layout else 520
        tlines = _wrap_lines(R.title_text(head), 100, SAFE_RIGHT - 70, 2)
        ev = _pop_block(tlines, 70, ty, 100, 0.1, dur)
        cap_y = ty + len(tlines) * 118 + 260
        ev += _captions(w2, starts[1], dur, y=min(cap_y, SAFE_BOTTOM - 140))
        person = (s["person"], ty - 66) if (person_layout and photo[2] == "person" and s.get("person")) else None
        segs.append((_scene(work, i, photo, {"num": i, "tag": s.get("tag"), "person": person,
                                             "sources": s.get("sources")},
                            ev, audio, dur, zoom_in=(i % 2 == 0)), dur))

    # ── 아웃트로 ──
    say = "매일 아침 7시, 정치 핫이슈 다섯 개. 팔로우하고 받아보세요."
    a, w, d = synth(say, os.path.join(work, "n_outro"), channel_id, "normal")
    dur = max(3.2, d + 0.8)
    ev = _pop_block(["매일 아침 7시", "정치 핫이슈", "5개만 콕"], 70, 640, 118, 0.1, dur, style="Big")
    ev += _pop_block([f"팔로우 {R.ACCOUNT}"], 70, 1110, 66, 0.6, dur, style="Big", color=R.YELLOW)

    def outro_extra(dd):
        note = "※ 언론 보도를 AI가 요약·논평했습니다. 한줄평은 이 계정의 의견입니다."
        yy = 1250
        for ln in R.wrap(dd, note, R.font(32, "regular"), SAFE_RIGHT - 70):
            dd.text((70, yy), ln, font=R.font(32, "regular"), fill=(220, 220, 225, 255),
                    stroke_width=1, stroke_fill=(0, 0, 0, 255))
            yy += 48
    segs.append((_scene(work, 99, pick(None, None, 30), {"extra": outro_extra}, ev, a, dur, False), dur))

    # ── 합치기: 슬라이드 전환 + 진행 바 (+ 배경음악) ──
    total = sum(d for _, d in segs) - XF * (len(segs) - 1)
    inputs, vf, af = [], [], []
    for p, _ in segs:
        inputs += ["-i", p]
    prev_v, prev_a, off = "0:v", "0:a", 0.0
    for k in range(1, len(segs)):
        off += segs[k - 1][1] - XF
        trans = "slideleft" if k % 2 else "slideup"
        vf.append(f"[{prev_v}][{k}:v]xfade=transition={trans}:duration={XF}:offset={off:.3f}[v{k}]")
        af.append(f"[{prev_a}][{k}:a]acrossfade=d={XF}[a{k}]")
        prev_v, prev_a = f"v{k}", f"a{k}"
    bar = os.path.join(work, "bar.png")
    Image.new("RGB", (RW, 14), R.ACCENT).save(bar)
    inputs += ["-loop", "1", "-framerate", str(FPS), "-t", f"{total:.3f}", "-i", bar]
    bi = len(segs)
    vf.append(f"[{prev_v}][{bi}:v]overlay=x='-W+W*t/{total:.3f}':y=0:eval=frame,format=yuv420p[vout]")
    bgm = "reels_bgm.mp3"
    if os.path.exists(bgm):
        inputs += ["-stream_loop", "-1", "-i", bgm]
        af.append(f"[{bi + 1}:a]volume=0.10,atrim=0:{total:.3f}[m];[{prev_a}][m]amix=inputs=2:duration=first:normalize=0[aout]")
    else:
        af.append(f"[{prev_a}]anull[aout]")
    out = os.path.join(out_dir, "reel.mp4")
    _run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(vf + af),
          "-map", "[vout]", "-map", "[aout]", "-t", f"{total:.3f}", "-r", str(FPS),
          "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out])
    print(f"[reels] {out} ({_dur(out):.1f}초, {os.path.getsize(out) / 1e6:.1f}MB)")
    return out


def reel_caption(content) -> str:
    lines = [content.get("reel_hook") or content["caption_hook"], ""]
    for i, s in enumerate(content["stories"], 1):
        lines.append(f"{i}. {s['headline']}")
    lines += ["", "※ 언론 보도를 AI가 요약·논평했습니다. 한줄평은 이 계정의 의견입니다.", "",
              " ".join(content.get("hashtags", [])[:10] + ["#릴스", "#정치뉴스"])]
    return "\n".join(lines)[:2200]
