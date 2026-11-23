"""쇼츠/릴스 전용 디자인 (1080x1920).

피드 카드를 작게 넣지 않고, 장면마다 '크게 읽히는 것 하나'만 보여준다.
reel.lines 의 각 줄: {"say": "읽을 문장", "show": {...}}
  show.type
    word   : {"label","text"(\n 줄바꿈, 줄당 7자 안팎)}         큰 글씨 키워드
    number : {"label","value":"12","unit":"개"}                 숫자 카운트업
    ratio  : {"label","part":6,"whole":12}                       점으로 비율
    date   : {"label","value":"11.19","sub"}                     달력
    steps  : {"label","items":[["날짜/번호","내용",완료1/0],...]}  진행 단계(최대 4)
    vs     : {"a":["쪽 이름","주장"],"b":[...]}                   양쪽 주장
    photo  : {"photo":번호,"text":"사진 위 띠 문구"}               사진 꽉 채움
  어느 장면이든 "bg_photo":번호 를 주면 어둡게 깐 사진 배경을 쓴다.
옛 형식(문자열 줄)도 받는다 → 사진/키워드 장면을 번갈아 자동 배정.
"""
import json
import math
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

sys.path.insert(0, os.path.dirname(__file__))
import poster_d as P  # noqa: E402
from reel_d import (FPS, H, W, Renderer, Scene, _silence, cover_fit, ease, stroke_text, tts)  # noqa: E402

STAGE = 330          # 큰 그림이 시작하는 높이
CAP_Y = 1350         # 자막 높이(쇼츠 아래쪽 버튼·제목에 안 가리게)
WHITE = (255, 255, 255)


def slide(t, delay=0.0, dur=0.35, dist=60):
    a = ease((t - delay) / dur)
    return a, int((1 - a) * dist)


class Shorts(Renderer):
    def __init__(self, content, cards_dir=None):
        super().__init__(content, cards_dir)
        self._bg = None

    def photo_at(self, i):
        """i = 카드 번호(0=표지). 그 카드 사진이 없으면 있는 사진 중에서 돌려 쓴다."""
        cards = self.c["cards"]
        try:
            i = int(i)
        except (TypeError, ValueError):
            i = 0
        if 0 <= i < len(cards):
            ph = cards[i].get("photo")
            if ph and ph.get("path") and os.path.exists(ph["path"]):
                return ph
        return self.photos[i % len(self.photos)] if self.photos else None

    # ---- 배경 ----
    def plain_bg(self):
        if self._bg is None:
            bg = Image.new("RGB", (W // 4, H // 4), self.C["ink"])
            g = Image.new("RGB", (W // 4, H // 4), self.C["accent"])
            m = Image.new("L", (W // 4, H // 4), 0)
            ImageDraw.Draw(m).ellipse((W // 4 - 220, -160, W // 4 + 120, 200), fill=120)
            ImageDraw.Draw(m).ellipse((-180, H // 4 - 150, 120, H // 4 + 140), fill=60)
            bg.paste(g, (0, 0), m.filter(ImageFilter.GaussianBlur(40)))
            self._bg = bg.resize((W, H), Image.BICUBIC)
        return self._bg.copy()

    def background(self, show, u):
        i = show.get("bg_photo")
        if i is not None and self.photos:
            ph = self.photo_at(i)
            img = self.kenburns(ph, (W, H), u, True, 0.3)
            img = ImageEnhance.Brightness(img).enhance(0.32)
            layer, mask = P.fade((W, H), 0.45, 0.85, self.C["ink"])
            img.paste(layer, (0, 0), mask)
            return img, ph
        return self.plain_bg(), None

    def label(self, d, text, t, y=STAGE + 40):
        a, off = slide(t, 0, 0.3, 200)
        if text:
            P.pill(d, (64 - off, y), P.clean(text), P.PX(44), self.C["accent"], WHITE, pad=(26, 14), r=10)

    # ---- 장면들 ----
    def s_word(self, d, img, sh, t):
        self.label(d, sh.get("label"), t)
        lines = P.clean(sh.get("text", "")).split("\n")
        size = 200
        while size > 90 and max(P.blen(d, ln, size) for ln in lines) > W - 150:
            size -= 6
        y = STAGE + 170
        for i, ln in enumerate(lines):
            a, off = slide(t, 0.12 + i * 0.14, 0.35, 70)
            if a <= 0:
                continue
            yy = y + off
            if i == len(lines) - 1 and len(lines) > 1:
                tw = P.blen(d, ln, size)
                d.rectangle((50, yy + size * 0.08, 50 + (tw + 30) * a, yy + size * 1.06), fill=self.C["accent"])
            P.btext(d, (64, yy), ln, size, WHITE)
            y += int(size * 1.12)

    def s_number(self, d, img, sh, t):
        self.label(d, sh.get("label"), t)
        try:
            target = float(str(sh.get("value", "0")).replace(",", ""))
        except ValueError:
            target = None
        k = ease((t - 0.1) / 0.9)
        txt = (f"{int(round(target * k)):,}" if target is not None and target == int(target)
               else f"{target * k:.1f}" if target is not None else str(sh.get("value")))
        size = 400
        unit = P.clean(sh.get("unit", ""))
        while size > 160 and P.blen(d, txt, size) + P.blen(d, unit, size // 2) > W - 150:
            size -= 10
        y = STAGE + 160
        x = P.btext(d, (64, y), txt, size, WHITE)
        if unit:
            P.btext(d, (x + 16, y + size * 0.45), unit, size // 2, self.C["accent"])

    def s_ratio(self, d, img, sh, t):
        self.label(d, sh.get("label"), t)
        part, whole = int(sh.get("part", 1)), int(sh.get("whole", 2))
        P.btext(d, (64, STAGE + 150), f"{part}", 260, self.C["accent"])
        x = 64 + P.blen(d, f"{part}", 260)
        P.btext(d, (x + 20, STAGE + 260), f"/ {whole}", 130, WHITE)
        cols = min(6, whole)
        rows = (whole + cols - 1) // cols
        dia = min(120, (W - 128 - (cols - 1) * 26) // cols)
        y0 = STAGE + 520
        for i in range(whole):
            cx = 64 + (i % cols) * (dia + 26)
            cy = y0 + (i // cols) * (dia + 26)
            on = i < part and t > 0.3 + i * 0.12
            if on:
                d.ellipse((cx, cy, cx + dia, cy + dia), fill=self.C["accent"])
            else:
                d.ellipse((cx, cy, cx + dia, cy + dia), outline=(120, 120, 132), width=8)

    def s_date(self, d, img, sh, t):
        val = str(sh.get("value", ""))
        mo, _, dy = val.partition(".")
        cw, ch = 560, 600
        card = Image.new("RGB", (cw, ch), WHITE)
        cd = ImageDraw.Draw(card)
        cd.rectangle((0, 0, cw, 150), fill=self.C["accent"])
        mt = f"{mo}월" if dy else ""
        P.btext(cd, ((cw - P.blen(cd, mt, 90)) / 2, 22), mt, 90, WHITE)
        big = dy or val
        s = 330
        while P.blen(cd, big, s) > cw - 60:
            s -= 10
        P.btext(cd, ((cw - P.blen(cd, big, s)) / 2, 150 + (ch - 150 - s * 1.05) / 2), big, s, self.C["ink"])
        a = ease(t / 0.4)
        hh = max(2, int(ch * a))
        card = card.resize((cw, hh), Image.BILINEAR)
        m = Image.new("L", (cw, hh), 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, cw - 1, hh - 1), 36, fill=255)
        x, y = (W - cw) // 2, STAGE + 40 + (ch - hh) // 2
        img.paste(card, (x, y), m)
        a2, off = slide(t, 0.3, 0.35, 50)
        if a2 > 0:
            lb = P.clean(sh.get("label", ""))
            s2 = 84
            while P.blen(d, lb, s2) > W - 128:
                s2 -= 4
            P.btext(d, ((W - P.blen(d, lb, s2)) / 2, STAGE + 700 + off), lb, s2, WHITE)
            sub = P.clean(sh.get("sub", ""))
            f = P.PB(46)
            d.text(((W - d.textlength(sub, font=f)) / 2, STAGE + 700 + s2 * 1.25 + off), sub, font=f,
                   fill=(200, 200, 210))

    def s_steps(self, d, img, sh, t):
        self.label(d, sh.get("label"), t)
        items = (sh.get("items") or [])[:4]
        n = len(items)
        step = min(270, 860 // max(1, n))
        y0 = STAGE + 190
        cx = 64 + 62
        cur = next((i for i, it in enumerate(items) if not (len(it) > 2 and it[2])), None)
        d.line((cx, y0 + 55, cx, y0 + 55 + step * (n - 1) * ease((t - 0.1) / 0.6)), fill=(90, 90, 104), width=8)
        for i, it in enumerate(items):
            a, off = slide(t, 0.15 + i * 0.22, 0.3, 50)
            if a <= 0:
                continue
            y = y0 + i * step
            done = len(it) > 2 and it[2]
            r = 62
            if done:
                d.ellipse((cx - r, y, cx + r, y + 2 * r), fill=self.C["accent"])
                k = ease((t - 0.3 - i * 0.22) / 0.25)
                if k > 0:   # 체크 표시
                    pts = [(cx - 26, y + r), (cx - 6, y + r + 22), (cx + 28, y + r - 20)]
                    if k < 0.5:
                        e = (pts[0][0] + (pts[1][0] - pts[0][0]) * k * 2, pts[0][1] + (pts[1][1] - pts[0][1]) * k * 2)
                        d.line([pts[0], e], fill=WHITE, width=12)
                    else:
                        kk = (k - 0.5) * 2
                        e = (pts[1][0] + (pts[2][0] - pts[1][0]) * kk, pts[1][1] + (pts[2][1] - pts[1][1]) * kk)
                        d.line([pts[0], pts[1], e], fill=WHITE, width=12, joint="curve")
            else:
                pulse = 1 + (0.08 * (1 + __import__("math").sin(t * 6)) if i == cur else 0)
                rr = r * pulse
                d.ellipse((cx - rr, y + r - rr, cx + rr, y + r + rr), fill=self.C["ink"],
                          outline=self.C["mark"] if i == cur else (120, 120, 132), width=8)
            x = cx + 90 + off
            d.text((x, y - 6), P.clean(str(it[0])), font=P.BH(58), fill=self.C["mark"] if i == cur else
                   (self.C["accent"] if done else (160, 160, 170)))
            txt = P.clean(str(it[1]))
            s = 80
            while P.blen(d, txt, s) > W - x - 50 and s > 44:
                s -= 2
            P.btext(d, (x, y + 66), txt, s, WHITE if (done or i == cur) else (180, 180, 190))

    def s_vs(self, d, img, sh, t):
        boxes = [(sh.get("a") or ["", ""], self.C["accent"], STAGE + 20, -1),
                 (sh.get("b") or ["", ""], (44, 44, 56), STAGE + 520, 1)]
        for (who, what), col, y, side in boxes:
            a, off = slide(t, 0.05 if side < 0 else 0.25, 0.35, 300)
            x = 64 + side * off
            d.rounded_rectangle((x, y, x + W - 128, y + 440), 36, fill=col)
            d.text((x + 50, y + 50), P.clean(who), font=P.PX(50), fill=WHITE if side < 0 else self.C["mark"])
            what = P.clean(what)
            s = 104
            lines = P.bwrap(d, what, s, W - 228)
            while len(lines) > 2 and s > 60:
                s -= 6
                lines = P.bwrap(d, what, s, W - 228)
            yy = y + 140
            for ln in lines:
                P.btext(d, (x + 50, yy), ln, s, WHITE)
                yy += int(s * 1.15)
        k = ease((t - 0.45) / 0.25)
        if k > 0:
            r = int(80 * k)
            cx, cy = W // 2, STAGE + 490
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=WHITE, outline=self.C["ink"], width=10)
            if k > 0.6:
                d.text((cx - d.textlength("VS", font=P.BH(70)) / 2, cy - 44), "VS", font=P.BH(70), fill=self.C["ink"])

    def frame_line(self, sc, t, prog):
        sh = sc.kw["show"]
        u = t / sc.dur
        if sh.get("type") == "photo" and self.photos:
            ph = self.photo_at(sh.get("photo", 0))
            img = Image.new("RGB", (W, H), self.C["ink"])
            p = self.kenburns(ph, (W, 1500), u, sc.kw.get("zin", True), 0.4)
            layer, mask = P.fade((W, 1500), 0.62, 0.98, self.C["ink"])
            p.paste(layer, (0, 0), mask)
            l2, m2 = P.fade((W, 300), 0, 1, (0, 0, 0), 170, 0)
            p.paste(l2, (0, 0), m2)
            img.paste(p)
            d = ImageDraw.Draw(img)
            txt = P.clean(sh.get("text", ""))
            if txt:
                s = 92
                while P.blen(d, txt, s) > W - 170 and s > 50:
                    s -= 4
                a, off = slide(t, 0.2, 0.35, W)
                y = 1110
                tw = P.blen(d, txt, s)
                d.rectangle((0 - off, y, 64 + tw + 40 - off, y + s * 1.35), fill=self.C["accent"])
                P.btext(d, (64 - off, y + s * 0.16), txt, s, WHITE)
            credit = ph.get("credit", "")
        else:
            img, ph = self.background(sh, u)
            d = ImageDraw.Draw(img)
            getattr(self, "s_" + sh.get("type", "word"), self.s_word)(d, img, sh, t)
            d = ImageDraw.Draw(img)
            credit = ph.get("credit", "") if ph else ""
        if credit:
            f = P.PM(22)
            d.text((W - 64 - d.textlength(credit, font=f), 222), credit, font=f, fill=(190, 190, 198))
        self.chrome(d, prog)
        P.pill(d, (64, 150), self.kicker, P.PX(30), (0, 0, 0), WHITE, pad=(18, 9), r=8)
        self.captions(d, sc.words, t, y=CAP_Y)
        return img

    # ---- 아이콘 배지: 의견 장면(말풍선)·결론 도장(판결 망치). Lucide 아이콘(ISC 라이선스) ----
    def badge(self, img, name, x, y, size, t=0.0, bg=None, fg=WHITE):
        a = ease(t / 0.3)
        sz = int(size * (0.6 + 0.4 * a))
        ox = x + (size - sz) // 2
        oy = y + (size - sz) // 2 + int(6 * math.sin(t * 5))
        d = ImageDraw.Draw(img)
        d.ellipse((ox, oy, ox + sz, oy + sz), fill=bg or self.C["ink"])
        ic = Image.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", f"icon_{name}.png"))
        ic = ic.convert("RGBA").resize((int(sz * 0.56), int(sz * 0.56)), Image.LANCZOS)
        tint = Image.new("RGBA", ic.size, fg + (255,))
        img.paste(tint, (ox + (sz - ic.width) // 2, oy + (sz - ic.height) // 2), ic.split()[3])

    def s_opinion(self, d, img, sh, t):
        """채널 의견 장면: 화면 전체를 채널 색으로 바꾸고 마스코트가 말한다"""
        a = ease(t / 0.22)
        d.rectangle((0, 0, W, H), fill=self.C["accent"])
        d.rectangle((0, 1180, W, H), fill=self.C["deep"])
        d.text((40, 250), "“", font=P.BH(520), fill=self.C["deep"])
        tag = (self.C["label"] + " " + str(sh.get("tag", ""))).strip()
        P.pill(d, (64 - int((1 - a) * 300), 380), tag, P.PX(46), self.C["ink"], WHITE, pad=(28, 14), r=10)
        txt = P.clean(sh.get("text", ""))
        size = 112
        wid = W - 128
        while size > 64 and len(P.bwrap(d, txt, size, wid)) > 3:
            size -= 6
        y = 520 + int((1 - a) * 40)
        for ln in P.bwrap(d, txt, size, wid)[:3]:
            P.btext(d, (64, y), ln, size, WHITE)
            y += int(size * 1.2)
        self.badge(img, "quote", 64, 1000, 190, t)
        d = ImageDraw.Draw(img)
        d.text((276, 1060), "이 채널의 생각", font=P.PB(44), fill=WHITE)
        d.text((276, 1118), self.C["label"], font=P.PM(30), fill=(255, 220, 220))

    def frame_punch(self, sc, t, prog):
        """결론: 어두운 배경 위에 큰 도장 + 결론 문장 + 동의/반대 유도"""
        img = self.plain_bg()
        d = ImageDraw.Draw(img)
        self.chrome(d, prog)
        a = ease(t / 0.3)
        lab = self.C["label"]
        f = P.BH(96)
        tw = int(d.textlength(lab, font=f))
        sw, sh_ = tw + 120, 220
        st = Image.new("RGBA", (sw, sh_), (0, 0, 0, 0))
        g = ImageDraw.Draw(st)
        g.rounded_rectangle((6, 6, sw - 6, sh_ - 6), 28, outline=self.C["accent"], width=16)
        g.text((60, 40), lab, font=f, fill=self.C["accent"])
        st = st.rotate(5 - (1 - a) * 18, expand=True, resample=Image.BICUBIC)
        k = 1.0 + (1 - a) * 0.5
        if k != 1.0:
            st = st.resize((int(st.width * k), int(st.height * k)), Image.LANCZOS)
        img.paste(st, (64, 330 - int((k - 1) * 60)), st)
        self.badge(img, "gavel", W - 270, 330, 200, t, bg=self.C["accent"])
        d = ImageDraw.Draw(img)
        d.text((64, 640), "결론", font=P.PB(44), fill=(200, 200, 210))
        words = sc.words[sc.kw.get("skip", 0):]
        text = " ".join(w[2] for w in words)
        size = 104
        while size > 66 and len(P.bwrap(d, text, size, W - 128)) > 5:
            size -= 6
        lines = P.bwrap(d, text, size, W - 128)
        shown = sum(1 for w in words if w[0] - 0.05 <= t)
        n, y = 0, 710
        for ln in lines:
            x = 64
            for p_ in ln.split():
                if n < shown:
                    x = P.btext(d, (x, y), p_ + " ", size, WHITE)
                n += 1
            y += int(size * 1.18)
        yb = max(y + 40, 1230)
        for i, (txt, on) in enumerate((("동의해요", True), ("아니에요", False))):
            x0 = 64 + i * 470
            d.rounded_rectangle((x0, yb, x0 + 430, yb + 120), 60,
                                fill=self.C["accent"] if on else None, outline=self.C["accent"], width=8)
            d.text((x0 + 215 - d.textlength(txt, font=P.PB(50)) / 2, yb + 28), txt, font=P.PB(50),
                   fill=WHITE if on else self.C["accent"])
        d.text((64, yb + 160), "어느 쪽이든 댓글로 남겨 주세요", font=P.PB(40), fill=WHITE)
        d.text((64, yb + 225), "한마디는 이 채널의 의견이에요", font=P.PM(30), fill=(160, 160, 170))
        return img

    def captions(self, d, words, t, y=CAP_Y):
        """한 번에 한 덩어리(최대 2줄), 말하는 단어 강조. 글씨 60px."""
        from reel_d import chunks
        groups = chunks(words, max_chars=22, max_words=7)
        cur = None
        for g in groups:
            if g[0][0] - 0.05 <= t:
                cur = g
        if not cur:
            return
        f = P.PX(60)
        sp = d.textlength(" ", font=f)
        lines, line, lw = [], [], 0
        for w in cur:
            tw = d.textlength(w[2], font=f)
            if line and lw + tw > W - 180:
                lines.append(line); line, lw = [], 0
            line.append((w, tw)); lw += tw + sp
        lines.append(line)
        yy = y
        for ln in lines:
            total = sum(tw for _, tw in ln) + sp * (len(ln) - 1)
            x = (W - total) / 2
            for (s, e, wtxt), tw in ln:
                if s - 0.03 <= t < e + 0.08:
                    d.rounded_rectangle((x - 10, yy - 4, x + tw + 10, yy + 80), 12, fill=self.C["accent"])
                    d.text((x, yy + 2), wtxt, font=f, fill=WHITE)
                else:
                    stroke_text(d, (x, yy + 2), wtxt, f, WHITE if s <= t else (215, 215, 222), 6)
                x += tw + sp
            yy += 94


def _auto_show(i, R):
    if R.photos and i % 2 == 0:
        return {"type": "photo", "photo": i // 2}
    tl = R.cover.get("title") or [""]
    return {"type": "word", "label": R.kicker, "text": "\n".join(tl) if isinstance(tl, list) else tl}


def plan(content, R, work):
    reel = content.get("reel") or {}
    out = []
    os.makedirs(work, exist_ok=True)
    hook = P.clean(reel.get("hook") or "")
    if hook:
        dur, words, wav = tts(hook, os.path.join(work, "a00.mp3"), "+0%")
        out.append((Scene("hook", dur + 0.7, words), wav))
    tz = P.clean(reel.get("teaser") or "")
    if tz:                                    # 결론 예고: 결론을 한 구절로 먼저 던진다
        ws, row = tz.split(), []
        rows = []
        for w_ in ws:
            if row and len(" ".join(row + [w_])) > 8:
                rows.append(" ".join(row)); row = []
            row.append(w_)
        rows.append(" ".join(row))
        dur, words, wav = tts("결론부터 말하면, " + tz, os.path.join(work, "a05.mp3"), "+6%")
        out.append((Scene("line", dur + 0.5, words, show={"type": "word", "label": "결론부터", "text": "\n".join(rows[:2])},
                          zin=True), wav))
    for i, ln in enumerate(reel.get("lines") or []):
        say, show = (ln.get("say", ""), ln.get("show")) if isinstance(ln, dict) else (ln, None)
        show = show or _auto_show(i, R)
        dur, words, wav = tts(P.clean(say), os.path.join(work, f"a{i + 1:02d}.mp3"), "-2%")
        out.append((Scene("line", dur + 0.6, words, show=show, zin=i % 4 < 2), wav))
    punch = P.clean(content["cards"][-1].get("punch") or "")
    if punch:
        lab = R.C["label"]
        dur, words, wav = tts(f"{lab}. {punch}", os.path.join(work, "a90.mp3"), "+0%")
        out.append((Scene("punch", dur + 1.4, words, skip=len(lab.split())), wav))
    end_wav = os.path.join(work, "a99.wav")
    _silence(end_wav, 2.4)
    out.append((Scene("end", 2.4), end_wav))
    return out


def build(content, out_mp4, work, cards_dir=None):
    R = Shorts(content, cards_dir)
    scenes = plan(content, R, work)
    parts = []
    for i, (sc, wav) in enumerate(scenes):
        p = os.path.join(work, f"seg{i:02d}.wav")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-af", f"apad=whole_dur={sc.dur:.3f}",
                        "-t", f"{sc.dur:.3f}", "-ar", "44100", "-ac", "1", p], check=True)
        parts.append(p)
    lst = os.path.join(work, "list.txt")
    open(lst, "w").write("".join(f"file '{os.path.abspath(p)}'\n" for p in parts))
    audio = os.path.join(work, "voice.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy",
                    audio], check=True)
    total = sum(sc.dur for sc, _ in scenes)
    enc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", audio,
                            "-af", "loudnorm=I=-15:TP=-1.5", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-shortest",
                            "-movflags", "+faststart", out_mp4], stdin=subprocess.PIPE)
    t0, prev, XF = 0.0, None, 0.18
    for sc, _ in scenes:
        n = int(round(sc.dur * FPS))
        last = None
        for k in range(n):
            t = k / FPS
            fr = R.draw(sc, t, (t0 + t) / total)
            if prev is not None and t < XF:
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


if __name__ == "__main__":
    post, out = sys.argv[1], sys.argv[2]
    c = json.load(open(os.path.join(post, "content.json"), encoding="utf-8"))
    print(build(c, out, os.path.join(os.path.dirname(os.path.abspath(out)), "_work_" + os.path.basename(out))))
