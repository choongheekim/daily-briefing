"""정치 계정 카드 D 디자인 — '뉴스 포스터'형.

- 표지: 사진을 꽉 채우고 큰 제목 + 하단에 '보수의 한마디/진보의 한마디' 띠
- 본문: 위쪽 사진(있으면 꽉 채움) + 큰 제목 + 짧은 본문, 위에 페이지 진행 막대
- 한마디 카드(새로 추가): 계정 색 전면, 따끔한 한마디를 크게
- 마무리: 다음에 볼 것 + 팔로우 안내 + 출처

content.json 형식은 기존과 같고, outro 에 punch(따끔한 한마디, 35자 이내)를 더 쓴다.
punch 가 있으면 마무리 앞에 한마디 카드가 한 장 추가된다.
"""
import json
import os
import re
import sys

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

W, H, M = 1080, 1350, 76
FD = os.path.join(os.path.dirname(__file__), "..", "fonts")

CH = {
    "right": dict(accent=(232, 40, 40), deep=(150, 16, 24), ink=(14, 13, 16), paper=(246, 243, 238),
                  mark=(255, 214, 0), handle="@bosu_morning", brand="BOSU MORNING", label="보수의 한마디"),
    "left": dict(accent=(28, 96, 255), deep=(14, 46, 150), ink=(9, 13, 28), paper=(240, 243, 249),
                 mark=(120, 230, 255), handle="@jinbo_morning", brand="JINBO MORNING", label="진보의 한마디"),
}
C = dict(CH["right"])
WHITE, GREY, MID = (255, 255, 255), (178, 178, 186), (110, 110, 120)
NOTE = "※ 언론 보도를 AI가 정리했어요. 한마디는 이 계정의 의견이에요."
DAYS = "월화수목금토일"


def _f(n, s):
    return ImageFont.truetype(os.path.join(FD, n), int(s))


BH = lambda s: _f("BlackHanSans-Regular.ttf", s)
PM = lambda s: _f("Pretendard-Medium.otf", s)
PB = lambda s: _f("Pretendard-Bold.otf", s)
PX = lambda s: _f("Pretendard-ExtraBold.otf", s)


# ---------- 글자 ----------
HANJA = {"北": "북", "南": "남", "美": "미", "中": "중", "日": "일", "韓": "한", "與": "여", "野": "야",
         "尹": "윤", "李": "이", "露": "러", "英": "영", "佛": "프", "獨": "독"}


def clean(t):
    return "".join(HANJA.get(ch, ch) for ch in (t or ""))


_MISS = {}


def _has(ch):
    """블랙한산스에 글자가 있는지(없으면 빈 네모가 그려짐) — fontTools 없이 확인"""
    if ch not in _MISS:
        f = BH(40)
        nd = (f.getbbox("\uE000"), f.getlength("\uE000"))
        _MISS[ch] = ch.isspace() or (f.getbbox(ch), f.getlength(ch)) != nd
    return _MISS[ch]


def _runs(text):
    """블랙한산스에 없는 글자(·, … 등)는 프리텐다드로 대신 그린다."""
    out = []
    for ch in clean(text):
        ok = ch == " " or _has(ch)
        if out and out[-1][1] == ok:
            out[-1][0] += ch
        else:
            out.append([ch, ok])
    return out


def blen(d, text, s):
    return sum(d.textlength(t, font=BH(s) if ok else PX(s)) for t, ok in _runs(text))


def btext(d, xy, text, s, fill):
    x, y = xy
    for t, ok in _runs(text):
        f = BH(s) if ok else PX(s)
        d.text((x, y + (0 if ok else s * 0.02)), t, font=f, fill=fill)
        x += d.textlength(t, font=f)
    return x

def toks(text):
    out, hi = [], False
    for part in re.split(r"(\*\*)", clean(text)):
        if part == "**":
            hi = not hi
            continue
        for w in re.split(r"(\s+)", part):
            if w:
                out.append((w, hi))
    return out


def wrap(d, text, f, width):
    lines = []
    for para in (text or "").split("\n"):
        cur, cw = [], 0
        for w, hi in toks(para):
            if w.isspace():
                if cur:
                    cur.append((" ", hi)); cw += d.textlength(" ", font=f)
                continue
            ww = d.textlength(w, font=f)
            if cw + ww > width and cur:
                while cur and cur[-1][0] == " ":
                    cur.pop()
                lines.append(cur); cur, cw = [], 0
            cur.append((w, hi)); cw += ww
        if cur:
            lines.append(cur)
    return lines


def text_block(d, xy, text, font_fn, size, width, color, hl="marker", gap=1.5, max_h=None, min_size=26,
               hl_color=None, hl_text=None):
    """**강조**는 형광펜처럼 칠한다. 칸이 모자라면 글자를 줄인다. 반환: 사용한 높이"""
    while True:
        f = font_fn(size)
        lines = wrap(d, text, f, width)
        lh = int(size * gap)
        if not max_h or len(lines) * lh <= max_h or size <= min_size:
            break
        size -= 1
    x0, y = xy
    for ln in lines:
        x = x0
        for w, hi in ln:
            tw = d.textlength(w, font=f)
            if hi and w != " ":
                if hl == "marker":
                    d.rectangle((x - 3, y + size * 0.52, x + tw + 3, y + size * 1.16), fill=hl_color or C["accent"])
                    d.text((x, y), w, font=f, fill=hl_text or color)
                else:
                    d.text((x, y), w, font=f, fill=hl_color or C["accent"])
            else:
                d.text((x, y), w, font=f, fill=color)
            x += tw
        y += lh
    return len(lines) * lh


def fit(d, lines, font_fn, start, width, min_size=40):
    s = start
    ln = (lambda t, z: blen(d, t, z)) if font_fn is BH else (lambda t, z: d.textlength(t, font=font_fn(z)))
    while s > min_size and max(ln(t, s) for t in lines) > width:
        s -= 2
    return s


def bwrap(d, text, s, width):
    lines, cur = [], ""
    for w in clean(text).split():
        t = (cur + " " + w).strip()
        if cur and blen(d, t, s) > width:
            lines.append(cur); cur = w
        else:
            cur = t
    if cur:
        lines.append(cur)
    return lines


def spaced(d, xy, text, f, fill, track=5):
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill)
        x += d.textlength(ch, font=f) + track
    return x


def pill(d, xy, text, f, bg, fg, pad=(20, 10), r=None):
    tw = d.textlength(text, font=f)
    x, y = xy
    hgt = f.size + pad[1] * 2
    d.rounded_rectangle((x, y, x + tw + pad[0] * 2, y + hgt), r if r is not None else hgt // 2, fill=bg)
    d.text((x + pad[0], y + pad[1] - f.size * 0.08), text, font=f, fill=fg)
    return x + tw + pad[0] * 2, y + hgt


# ---------- 사진 ----------
def photo_fill(ph, size, cy=None):
    im = Image.open(ph["path"]).convert("RGB")
    im = ImageOps.fit(im, size, Image.LANCZOS, centering=(0.5, cy if cy is not None else ph.get("cy", 0.4)))
    return ImageEnhance.Contrast(ImageEnhance.Color(im).enhance(1.05)).enhance(1.05)


def fade(size, start, end, color, top_alpha=0, bottom_alpha=255):
    """세로 그라데이션 덧칠 (start~end 비율 구간에서 투명→불투명)"""
    w, h = size
    g = Image.new("L", (1, h), 0)
    for y in range(h):
        t = (y / h - start) / max(1e-6, end - start)
        t = max(0.0, min(1.0, t))
        t = t * t * (3 - 2 * t)
        g.putpixel((0, y), int(top_alpha + (bottom_alpha - top_alpha) * t))
    mask = g.resize((w, h))
    layer = Image.new("RGB", (w, h), color)
    return layer, mask


# ---------- 공통 틀 ----------
def header(d, page, total, dark=True):
    fg = WHITE if dark else C["ink"]
    # 진행 막대
    seg_w = (W - 2 * M - (total - 1) * 8) / total
    for i in range(total):
        x = M + i * (seg_w + 8)
        on = i < page
        d.rounded_rectangle((x, 34, x + seg_w, 40), 3,
                            fill=(C["accent"] if on else ((255, 255, 255) if dark else (0, 0, 0))) if on
                            else ((70, 70, 78) if dark else (210, 206, 200)))
    spaced(d, (M, 62), C["brand"], PX(22), fg, 6)
    t = f"{page:02d} / {total:02d}"
    d.text((W - M - d.textlength(t, font=PX(22)), 62), t, font=PX(22), fill=fg)


def footer(d, sources=None, credit=None, dark=True):
    col = (150, 150, 160) if dark else (120, 116, 110)
    d.line((M, H - 92, W - M, H - 92), fill=(60, 60, 68) if dark else (214, 210, 204), width=2)
    d.text((M, H - 70), C["handle"], font=PX(24), fill=WHITE if dark else C["ink"])
    parts = []
    if sources:
        parts.append("출처 " + ", ".join(sources[:3]))
    if credit:
        parts.append(credit)
    t = "  |  ".join(parts)
    f = PM(19)
    while d.textlength(t, font=f) > W - 2 * M - 260 and len(t) > 10:
        t = t[:-2]
    d.text((W - M - d.textlength(t, font=f), H - 66), t, font=f, fill=col)


def base(dark=True, color=None):
    img = Image.new("RGB", (W, H), color or (C["ink"] if dark else C["paper"]))
    return img, ImageDraw.Draw(img)


def top_photo(img, ph, h, dark=True):
    """카드 위쪽에 사진을 꽉 채우고 아래로 바탕색에 녹인다."""
    p = photo_fill(ph, (W, h))
    bg = C["ink"] if dark else C["paper"]
    layer, mask = fade((W, h), 0.55, 1.0, bg)
    p.paste(layer, (0, 0), mask)
    # 머리글 읽히게 위쪽 살짝 어둡게
    l2, m2 = fade((W, 160), 0.0, 1.0, (0, 0, 0), top_alpha=150, bottom_alpha=0)
    p.paste(l2, (0, 0), m2)
    img.paste(p, (0, 0))


def big_index(d, n, dark=True):
    """사진 없는 카드 배경의 큰 숫자"""
    f = BH(520)
    t = f"{n:02d}"
    d.text((W - M - d.textlength(t, font=f) + 30, 70), t, font=f,
           fill=(30, 30, 36) if dark else (234, 230, 223))


def title(d, y, text, n=None, dark=True, size=92, width=W - 2 * M):
    fg = WHITE if dark else C["ink"]
    lines = text.split("\n")
    s = fit(d, lines, BH, size, width, 54)
    x = M
    if n is not None:
        d.rectangle((M, y + 6, M + 10, y + s * 1.12 * len(lines) - 6), fill=C["accent"])
        x = M + 34
        s = fit(d, lines, BH, s, width - 34, 54)
    for i, ln in enumerate(lines):
        btext(d, (x, y + i * s * 1.12), ln, s, fg)
    return y + int(s * 1.12 * len(lines))


# ---------- 카드 ----------
def cover(card, total, date, punch):
    ph = card.get("photo")
    img, d = base(True)
    if ph:
        p = photo_fill(ph, (W, H), ph.get("cy", 0.32))
        p = ImageEnhance.Brightness(p).enhance(0.92)
        layer, mask = fade((W, H), 0.30, 0.78, C["ink"])
        p.paste(layer, (0, 0), mask)
        l2, m2 = fade((W, 200), 0, 1, (0, 0, 0), 160, 0)
        p.paste(l2, (0, 0), m2)
        img.paste(p)
    else:
        img.paste(C["deep"], (0, 0, W, H))
    d = ImageDraw.Draw(img)
    header(d, 1, total)
    # 날짜 딱지
    dt = date
    pill(d, (M, 112), dt, PX(26), C["accent"], WHITE, pad=(18, 9), r=6)

    # 제목 (아래에서 위로 쌓는다)
    tl = card.get("title") or []
    if isinstance(tl, str):
        tl = tl.split("\n")
    s = fit(d, tl, BH, 150, W - 2 * M - 30, 80)
    punch_h = 0
    if punch:
        pf = PX(44)
        plines = wrap(d, punch, pf, W - 2 * M - 64)
        if len(plines) > 2:
            pf = PX(38); plines = wrap(d, punch, pf, W - 2 * M - 64)
        punch_h = 70 + len(plines) * int(pf.size * 1.32) + 40
    y_box = H - 110 - punch_h
    ty = y_box - 46 - int(s * 1.12) * len(tl)
    kick = card.get("kicker", "")
    d.text((M, ty - 62), kick, font=PX(32), fill=C["mark"])
    for i, ln in enumerate(tl):
        yy = ty + i * int(s * 1.12)
        if i == len(tl) - 1 and len(tl) > 1:
            tw = blen(d, ln, s)
            d.rectangle((M - 14, yy + s * 0.06, M + tw + 14, yy + s * 1.06), fill=C["accent"])
        btext(d, (M, yy), ln, s, WHITE)

    if punch:
        x0, x1 = M, W - M
        d.rounded_rectangle((x0, y_box, x1, y_box + punch_h - 30), 18, fill=WHITE)
        lab = C["label"]
        pill(d, (x0 + 28, y_box - 24), lab, PX(28), C["accent"], WHITE, pad=(20, 10), r=8)
        yy = y_box + 46
        for ln in plines:
            x = x0 + 32
            for w, _ in ln:
                d.text((x, yy), w, font=pf, fill=C["ink"])
                x += d.textlength(w, font=pf)
            yy += int(pf.size * 1.32)
    # 넘김 안내
    t = "넘겨서 보기  →"
    d.text((W - M - d.textlength(t, font=PB(24)), H - 68), t, font=PB(24), fill=(220, 220, 226))
    d.text((M, H - 68), C["handle"], font=PX(24), fill=WHITE)
    if ph:
        cf = PM(17)
        cr = ph.get("credit", "")
        d.text((W - M - d.textlength(cr, font=cf), 120), cr, font=cf, fill=(200, 200, 206))
    return img


def story(card, n, total):
    ph = card.get("photo")
    img, d = base(True)
    if ph:
        top_photo(img, ph, 600)
        d = ImageDraw.Draw(img)
        y = 560
    else:
        big_index(d, n)
        y = 190
    header(d, n, total)
    y = title(d, y, card["title"], n) + 40
    body = card.get("body") or []
    if isinstance(body, str):
        body = [body]
    note = card.get("note")
    avail = H - 120 - y - (200 if note else 0)
    size = 40
    while size > 28:
        tot = sum(len(wrap(d, p_, PM(size), W - 2 * M)) * int(size * 1.55) + 26 for p_ in body)
        if tot <= avail:
            break
        size -= 1
    for para in body:
        y += text_block(d, (M, y), para, PM, size, W - 2 * M, (232, 232, 238), gap=1.55,
                        hl_color=C["accent"], hl_text=WHITE) + 26
    if note:
        y = max(y + 6, H - 120 - 180)
        d.rectangle((M, y, M + 8, y + 150), fill=C["mark"])
        d.text((M + 32, y + 4), note.get("label", ""), font=PX(26), fill=C["mark"])
        text_block(d, (M + 32, y + 48), note.get("text", ""), PB, 31, W - 2 * M - 40, WHITE, hl="color",
                   gap=1.45, max_h=104, min_size=24, hl_color=C["mark"])
    footer(d, card.get("sources"), (ph or {}).get("credit"))
    return img


def profile(card, n, total):
    ph = card.get("photo")
    img, d = base(False)
    if ph:
        top_photo(img, ph, 560, dark=False)
        d = ImageDraw.Draw(img)
        y = 500
    else:
        big_index(d, n, False)
        y = 190
    header(d, n, total, dark=bool(ph))
    # 머리글이 사진 위면 흰색, 아니면 검정 — 사진 있을 때 header(dark=True)
    y = title(d, y, card["title"], n, dark=False) + 34
    rows = card.get("rows") or []
    rh = min(92, (H - 130 - y) // max(1, len(rows)))
    for k, v in rows:
        d.line((M, y, W - M, y), fill=(214, 210, 204), width=2)
        d.text((M, y + (rh - 30) / 2 - 2), k, font=PX(28), fill=C["accent"])
        text_block(d, (M + 230, y + (rh - 38) / 2 - 4), v, PB, 37, W - 2 * M - 230, C["ink"], gap=1.2,
                   max_h=rh - 10, min_size=26)
        y += rh
    d.line((M, y, W - M, y), fill=(214, 210, 204), width=2)
    footer(d, card.get("sources"), (ph or {}).get("credit"), dark=False)
    return img


def timeline(card, n, total):
    ph = card.get("photo")
    img, d = base(False)
    if ph:
        top_photo(img, ph, 470, dark=False)
        d = ImageDraw.Draw(img)
        y = 420
    else:
        big_index(d, n, False)
        y = 190
    header(d, n, total, dark=bool(ph))
    y = title(d, y, card["title"], n, dark=False) + 50
    items = card.get("items") or []
    step = min(150, (H - 140 - y) // max(1, len(items)))
    lx = M + 196
    d.line((lx, y + 20, lx, y + step * (len(items) - 1) + 20), fill=C["ink"], width=4)
    for i, it in enumerate(items):
        last = i == len(items) - 1
        yy = y + i * step
        df = BH(46)
        d.text((M, yy - 4), it.get("date", ""), font=df, fill=C["accent"])
        if last:
            d.ellipse((lx - 17, yy + 3, lx + 17, yy + 37), fill=C["accent"])
        else:
            d.ellipse((lx - 11, yy + 9, lx + 11, yy + 31), fill=C["paper"], outline=C["ink"], width=5)
        text_block(d, (lx + 44, yy + 2), it.get("text", ""), PB if not last else PX, 34, W - M - lx - 44,
                   C["ink"], hl="color", gap=1.35, max_h=step - 16, min_size=26)
    footer(d, card.get("sources"), (ph or {}).get("credit"), dark=False)
    return img


def numbers(card, n, total):
    ph = card.get("photo")
    img, d = base(True, C["accent"])
    if ph:
        p = photo_fill(ph, (W, 520))
        p = ImageOps.colorize(ImageOps.grayscale(p), black=C["deep"], white=C["accent"]).convert("RGB")
        layer, mask = fade((W, 520), 0.4, 1.0, C["accent"])
        p.paste(layer, (0, 0), mask)
        img.paste(p)
        d = ImageDraw.Draw(img)
        y = 400
    else:
        y = 190
    header(d, n, total)
    y = title(d, y, card["title"]) + 44
    items = (card.get("items") or [])[:4]
    cols = 2
    gw = (W - 2 * M - 24) // cols
    rows = (len(items) + 1) // 2
    gh = min(300, (H - 130 - y - 24 * (rows - 1)) // max(1, rows))
    for i, it in enumerate(items):
        x = M + (i % 2) * (gw + 24)
        yy = y + (i // 2) * (gh + 24)
        d.rounded_rectangle((x, yy, x + gw, yy + gh), 22, fill=C["ink"])
        v = it.get("value", "")
        s = fit(d, [v], BH, 112, gw - 60, 50)
        btext(d, (x + 34, yy + 30), v, s, WHITE)
        text_block(d, (x + 34, yy + 40 + s * 1.15), it.get("label", ""), PB, 28, gw - 60, (200, 200, 210),
                   gap=1.35, max_h=gh - s * 1.15 - 60, min_size=22)
    footer(d, card.get("sources"), (ph or {}).get("credit"))
    return img


def debate(card, n, total):
    img, d = base(True)
    big_index(d, n)
    header(d, n, total)
    y = title(d, 190, card["title"], n) + 34
    y += text_block(d, (M, y), card.get("lead", ""), PB, 36, W - 2 * M, (232, 232, 238), gap=1.5, max_h=170,
                    min_size=28, hl_color=C["accent"], hl_text=WHITE) + 40
    sides = [card.get("left") or {}, card.get("right") or {}]
    gw = (W - 2 * M - 40) // 2
    foot = card.get("foot")
    # 먼저 내용 높이 계산
    hs = []
    for sd in sides:
        s_ = fit(d, [sd.get("label", "")], BH, 48, gw - 60, 30)
        hh = 50 + s_ * 1.25
        for pnt in sd.get("points") or []:
            hh += len(wrap(d, pnt, PB(35), gw - 106)) * int(35 * 1.4) + 22
        hs.append(hh + 20)
    bh = min(max(hs), H - 130 - y - (150 if foot else 20))
    foot_h = (len(wrap(d, foot, PM(28), W - 2 * M)) * 42 + 34) if foot else 0
    spare = H - 130 - y - bh - foot_h
    if spare > 60:
        bh = min(bh + spare * 0.35, bh + 160)
        y += int((H - 130 - y - bh - foot_h) * 0.4)
    for i, sd in enumerate(sides):
        x = M + i * (gw + 40)
        d.rounded_rectangle((x, y, x + gw, y + bh), 22, fill=(32, 32, 40))
        d.rounded_rectangle((x, y, x + gw, y + 10), 4, fill=C["accent"] if i == 0 else C["mark"])
        lab = sd.get("label", "")
        s_ = fit(d, [lab], BH, 48, gw - 60, 30)
        btext(d, (x + 30, y + 36), lab, s_, WHITE)
        yy = y + 50 + s_ * 1.25
        for pnt in sd.get("points") or []:
            d.text((x + 30, yy), "—", font=PX(30), fill=C["accent"] if i == 0 else C["mark"])
            hh = text_block(d, (x + 76, yy), pnt, PB, 35, gw - 106, WHITE, gap=1.4, max_h=200, min_size=24)
            yy += hh + 22
    cx, cy = W // 2, int(y + bh / 2)
    d.ellipse((cx - 40, cy - 40, cx + 40, cy + 40), fill=WHITE, outline=C["ink"], width=6)
    d.text((cx - d.textlength("VS", font=BH(36)) / 2, cy - 23), "VS", font=BH(36), fill=C["ink"])
    y += bh + 34
    if foot:
        text_block(d, (M, y), foot, PM, 28, W - 2 * M, (170, 170, 180), gap=1.5, max_h=120,
                   min_size=22)
    footer(d, card.get("sources"))
    return img


def punch_card(card, n, total):
    img, d = base(True, C["accent"])
    # 큰 따옴표
    d.text((M - 10, 70), "“", font=BH(440), fill=C["deep"])
    header(d, n, total)
    y = 330
    pill(d, (M, y), C["label"], PX(32), C["ink"], WHITE, pad=(22, 12), r=8)
    y += 110
    punch = card.get("punch", "")
    size = 104
    while True:
        lines = bwrap(d, punch, size, W - 2 * M)
        if len(lines) <= 4 or size <= 64:
            break
        size -= 4
    for ln in lines:
        btext(d, (M, y), ln, size, WHITE)
        y += int(size * 1.2)
    y += 36
    d.rectangle((M, y, M + 120, y + 8), fill=C["ink"])
    y += 46
    op = card.get("opinion", "")
    text_block(d, (M, y), op.replace("**", ""), PB, 36, W - 2 * M, (255, 240, 236), gap=1.55,
               max_h=H - 140 - y - 60, min_size=26)
    d.text((M, H - 140), "이 계정의 의견이에요. 동의하시나요? 댓글로 의견 남겨 주세요.", font=PB(25), fill=C["ink"])
    footer_line(d)
    return img


def footer_line(d):
    d.line((M, H - 92, W - M, H - 92), fill=C["deep"], width=2)
    d.text((M, H - 70), C["handle"], font=PX(24), fill=WHITE)


def outro(card, n, total):
    img, d = base(True)
    header(d, n, total)
    y = 170
    pill(d, (M, y), "다음에 볼 것", PX(28), C["accent"], WHITE, pad=(20, 10), r=8)
    big = card.get("big", "")
    s = fit(d, [big], BH, 250, W - 2 * M, 100)
    btext(d, (M - 6, y + 70), big, s, WHITE)
    y += 80 + int(s * 1.08)
    t = card.get("title", "").split("\n")[-1]
    y = title(d, y, t, dark=True, size=76) + 26
    y += text_block(d, (M, y), card.get("body", ""), PM, 36, W - 2 * M, (220, 220, 228), gap=1.55,
                    max_h=260, min_size=28, hl_color=C["accent"], hl_text=WHITE) + 40
    # 팔로우 박스
    by = max(y, H - 470)
    d.rounded_rectangle((M, by, W - M, by + 190), 22, fill=WHITE)
    d.text((M + 36, by + 34), "매일 아침 7시, 정치 이슈 하나를 깊게", font=PX(36), fill=C["ink"])
    d.text((M + 36, by + 92), "팔로우하고 저장해 두세요", font=PB(30), fill=MID)
    hx = W - M - 36 - d.textlength(C["handle"], font=BH(40))
    d.text((hx, by + 120), C["handle"], font=BH(40), fill=C["accent"])
    yy = by + 220
    src = card.get("sources") or []
    text_block(d, (M, yy), "출처  " + " · ".join(src), PM, 22, W - 2 * M, (150, 150, 160), gap=1.4, max_h=64,
               min_size=18)
    d.text((M, yy + 70), NOTE, font=PM(21), fill=(130, 130, 140))
    footer_line(d)
    return img


def _date_label(c):
    ds = str(c.get("date") or "")
    m = re.match(r"(\d{4})-?(\d{2})-?(\d{2})", ds)
    if not m:
        return "오늘의 정치"
    import datetime
    dt = datetime.date(int(m[1]), int(m[2]), int(m[3]))
    return f"{dt.month}.{dt.day} ({DAYS[dt.weekday()]}) 오늘의 정치"


def set_channel(cid):
    C.clear()
    C.update(CH[cid])


def render(post_dir, out_dir=None, channel=None):
    c = json.load(open(os.path.join(post_dir, "content.json"), encoding="utf-8"))
    set_channel(channel or c.get("channel") or "right")
    out_dir = out_dir or post_dir
    os.makedirs(out_dir, exist_ok=True)
    cards = list(c["cards"])
    outro_c = cards[-1] if cards[-1]["type"] == "outro" else {}
    punch = outro_c.get("punch")
    seq = cards[:-1] + ([dict(outro_c, type="punch")] if punch else []) + ([outro_c] if outro_c else [])
    total = len(seq)
    fn = {"story": story, "profile": profile, "timeline": timeline, "numbers": numbers, "debate": debate,
          "punch": punch_card, "outro": outro}
    out = []
    for i, card in enumerate(seq, 1):
        if card["type"] == "cover":
            img = cover(card, total, _date_label(c), punch)
        else:   # 모르는 종류는 본문 카드로 그림(본문이 없어도 제목만으로)
            img = fn.get(card["type"], story)(card, i, total)
        f = os.path.join(out_dir, f"{i:02d}.jpg")
        img.save(f, quality=92, optimize=True, progressive=True)
        out.append(f)
    return out


if __name__ == "__main__":
    print(render(sys.argv[1], *(sys.argv[2:3] or [None]), *(sys.argv[3:4] or [None])))
