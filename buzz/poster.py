"""그래픽 포스터형(C) 카드 — 한 게시물 = 한 주제를 7장으로 깊게. (hottopic-zip 디자인을 정치 계정용으로)

set_channel("right"|"left") 로 계정 색·이름을 바꾼다. 보수=빨강(hottopic 그대로), 진보=파랑(크림·검정 유지).

카드 종류: cover / profile / story / numbers / timeline / debate / outro
본문 텍스트에서 **굵게** 감싼 부분은 강조색으로 칠한다.
"""
import json
import os
import re
import sys

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

W, H, M = 1080, 1350, 72
FD = os.path.join(os.path.dirname(__file__), "..", "fonts")
HANDLE = os.getenv("BUZZ_HANDLE", "@bosu_morning")
DUO_DARK = (58, 14, 30)            # 자료사진 듀오톤 어두운 색
CTA = ("매일 아침, 오늘의 정치 이슈 하나를 깊게", "저장해 두고 친구에게 공유해 주세요")
NOTE = "※ 언론 보도를 AI가 정리했어요. 한줄평은 이 계정의 의견이에요."
OPINION_LABEL = "보수의 한줄평"

RED, CREAM, DARK = (255, 78, 56), (255, 244, 230), (30, 12, 20)
PINK, SOFT = (255, 214, 196), (246, 230, 212)
PAPER, INK, ORANGE, BEIGE = (244, 240, 232), (20, 20, 22), (255, 92, 40), (232, 226, 214)
IVORY, BLACK, WINE, GOLD = (250, 247, 240), (17, 17, 19), (158, 30, 44), (214, 176, 110)

STYLES = {
    "C": dict(brand="HOT TOPIC", title="BH", photo="duo",
              themes={"red": (RED, CREAM, DARK, (255, 222, 210)), "cream": (CREAM, DARK, RED, (120, 92, 88)),
                      "dark": (DARK, CREAM, RED, (190, 170, 170))},
              order=dict(cover="red", profile="cream", story="dark", numbers="red", timeline="cream",
                         debate="dark", outro="red"),
              box_a=(RED, DARK, CREAM), box_b=(CREAM, RED, DARK), tiles=[(CREAM, DARK), (DARK, CREAM)],
              tile_num=RED, numbers_title=CREAM, big=CREAM, outro_title=DARK, outro_text=DARK, outro_cta=CREAM),
    "B": dict(brand="BUZZ REPORT", title="PX", photo="color",
              themes={"paper": (PAPER, INK, ORANGE, (120, 115, 105))},
              order=dict(cover="paper", profile="paper", story="paper", numbers="paper", timeline="paper",
                         debate="paper", outro="paper"),
              box_a=(ORANGE, INK, (255, 255, 255)), box_b=(BEIGE, ORANGE, INK), tiles=[(INK, PAPER), (BEIGE, INK)],
              tile_num=ORANGE, numbers_title=INK, big=ORANGE, outro_title=INK, outro_text=INK, outro_cta=ORANGE),
    "A": dict(brand="THE BUZZ", title="SR", photo="color",
              themes={"ivory": (IVORY, BLACK, WINE, (125, 118, 110)), "black": (BLACK, IVORY, GOLD, (165, 160, 152))},
              order=dict(cover="black", profile="ivory", story="black", numbers="ivory", timeline="ivory",
                         debate="black", outro="black"),
              box_a=(WINE, GOLD, IVORY), box_b=(IVORY, WINE, BLACK), tiles=[(BLACK, IVORY), ((236, 230, 220), BLACK)],
              tile_num=GOLD, numbers_title=WINE, big=GOLD, outro_title=IVORY, outro_text=(215, 210, 202), outro_cta=GOLD),
}
ST = STYLES["C"]
THEMES = ST["themes"]

CHANNELS = {
    # 강조색, 강조색 위 보조글자색, 자료사진 듀오톤(어두운/밝은)
    "right": dict(accent=(255, 78, 56), on_accent=(255, 222, 210), duo=((58, 14, 30), (255, 214, 196)),
                  handle="@bosu_morning", brand="BOSU MORNING", label="보수의 한줄평"),
    "left": dict(accent=(38, 104, 255), on_accent=(214, 226, 255), duo=((12, 24, 64), (200, 216, 255)),
                 handle="@jinbo_morning", brand="JINBO MORNING", label="진보의 한줄평"),
}


def set_channel(cid: str):
    """계정별 색·이름 적용(빨강 자리를 계정 색으로, 크림·검정은 그대로)."""
    global RED, PINK, DUO_DARK, HANDLE, OPINION_LABEL
    ch = CHANNELS[cid]
    RED, (DUO_DARK, PINK) = ch["accent"], ch["duo"]
    HANDLE, OPINION_LABEL = ch["handle"], ch["label"]
    STYLES["C"].update(
        brand=ch["brand"],
        themes={"red": (RED, CREAM, DARK, ch["on_accent"]), "cream": (CREAM, DARK, RED, (120, 92, 88)),
                "dark": (DARK, CREAM, RED, (190, 170, 170))},
        box_a=(RED, DARK, CREAM), box_b=(CREAM, RED, DARK), tile_num=RED)


def _f(name, s):
    return ImageFont.truetype(os.path.join(FD, name), s)


BH = lambda s: _f("BlackHanSans-Regular.ttf", s)
PM = lambda s: _f("Pretendard-Medium.otf", s)
PB = lambda s: _f("Pretendard-Bold.otf", s)
PX = lambda s: _f("Pretendard-ExtraBold.otf", s)


def SR(s):
    f = _f("NotoSerifKR-Variable.ttf", s)
    try:
        f.set_variation_by_axes([900])
    except Exception:
        pass
    return f


def TF(s):
    return {"BH": BH, "PX": PX, "SR": SR}[ST["title"]](s)


# ---------- 글자 도구 ----------
def _tokens(text):
    """'**강조**' → [(단어, 강조여부)]"""
    out, hi = [], False
    for part in re.split(r"(\*\*)", text):
        if part == "**":
            hi = not hi
            continue
        for w in re.split(r"(\s+)", part):
            if w:
                out.append((w, hi))
    return out


def rich_lines(d, text, font, width):
    if "\n" in text:
        out = []
        for para in text.split("\n"):
            out += rich_lines(d, para, font, width)
        return out
    lines, cur, cw = [], [], 0
    for w, hi in _tokens(text):
        if w.isspace():
            if cur:
                cur.append((" ", hi))
                cw += d.textlength(" ", font=font)
            continue
        ww = d.textlength(w, font=font)
        if cw + ww > width and cur:
            while cur and cur[-1][0] == " ":
                cw -= d.textlength(" ", font=font)
                cur.pop()
            lines.append(cur)
            cur, cw = [], 0
        cur.append((w, hi))
        cw += ww
    if cur:
        lines.append(cur)
    return lines


def rich(d, xy, text, font_fn, size, width, color, accent, gap=1.5, max_h=None, min_size=24, hl_bg=None):
    while True:
        f = font_fn(size)
        lines = rich_lines(d, text, f, width)
        lh = int(size * gap)
        if not max_h or len(lines) * lh <= max_h or size <= min_size:
            break
        size -= 1
    x0, y = xy
    for ln in lines:
        x = x0
        for w, hi in ln:
            tw = d.textlength(w, font=f)
            if hi and hl_bg and w != " ":
                d.rectangle((x - 2, y + size * 0.55, x + tw + 2, y + size * 1.12), fill=hl_bg)
            d.text((x, y), w, font=f, fill=accent if (hi and not hl_bg) else color)
            x += tw
        y += lh
    return len(lines) * lh, size


def fit_size(d, text, font_fn, start, width):
    s = start
    while s > 20 and max(d.textlength(t, font=font_fn(s)) for t in text.split("\n")) > width:
        s -= 2
    return s


def spaced(d, xy, text, f, fill, track=6):
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill)
        x += d.textlength(ch, font=f) + track
    return x


# ---------- 사진 ----------
def duotone(path, size, dark, light, shape="rect", r=0, cy=0.42, mode=None):
    src = ImageOps.fit(Image.open(path).convert("RGB"), size, Image.LANCZOS, centering=(0.5, cy))
    if (mode or ST["photo"]) == "duo":
        g = ImageOps.autocontrast(ImageEnhance.Contrast(ImageOps.grayscale(src)).enhance(1.15), cutoff=1)
        img = ImageOps.colorize(g, black=dark, white=light)
    else:
        img = ImageEnhance.Contrast(src).enhance(1.04)
    m = Image.new("L", size, 0)
    md = ImageDraw.Draw(m)
    if shape == "circle":
        md.ellipse((0, 0, size[0] - 1, size[1] - 1), fill=255)
    else:
        md.rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), r, fill=255)
    return img, m


def put_photo(img, ph, xy, size, shape="rect", r=28, caption=None):
    """카드에 사진 붙이기. 실제 사진(mode=color)은 원래 색, 그 외는 스타일 따라 듀오톤."""
    p, m = duotone(ph["path"], size, DUO_DARK, PINK, shape, r, cy=ph.get("cy", 0.42), mode=ph.get("mode"))
    img.paste(p, xy, m)
    d = ImageDraw.Draw(img)
    cap = caption or ph.get("caption")
    if cap and shape == "rect":
        f = PB(22)
        tw = d.textlength(cap, font=f)
        x, y = xy[0] + 18, xy[1] + size[1] - 56
        d.rounded_rectangle((x, y, x + tw + 28, y + 40), 20, fill=(20, 20, 22))
        d.text((x + 14, y + 7), cap, font=f, fill=(255, 255, 255))
    return d


def is_portrait(ph) -> bool:
    """세로 사진(인물 사진 대부분)은 가로로 긴 띠에 넣으면 얼굴만 크게 잘림 → 동그라미로 넣는다."""
    try:
        with Image.open(ph["path"]) as im:
            return im.height > im.width * 0.95
    except Exception:
        return False


def sticker(lines, diameter, bg, fg, angle=-12):
    s = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
    d = ImageDraw.Draw(s)
    d.ellipse((0, 0, diameter - 1, diameter - 1), fill=bg)
    sizes = [int(diameter * k) for k in (0.15, 0.2, 0.17)][: len(lines)]
    total = sum(int(z * 1.12) for z in sizes)
    y = (diameter - total) / 2
    for t, z in zip(lines, sizes):
        f = BH(z)
        d.text(((diameter - d.textlength(t, font=f)) / 2, y), t, font=f, fill=fg)
        y += int(z * 1.12)
    return s.rotate(angle, resample=Image.BICUBIC, expand=True)


# ---------- 공통 틀 ----------
def canvas(kind):
    bg, fg, ac, sub = ST["themes"][ST["order"][kind]]
    img = Image.new("RGB", (W, H), bg)
    return img, ImageDraw.Draw(img), (bg, fg, ac, sub)


def frame(d, pal, code, page, total, sources=None, credit=None):
    bg, fg, ac, sub = pal
    spaced(d, (M, 60), ST["brand"], PX(26), fg, 7)
    t = f"{code}  {page:02d}/{total:02d}"
    d.text((W - M - d.textlength(t, font=PX(24)), 62), t, font=PX(24), fill=fg)
    d.line((M, 106, W - M, 106), fill=fg, width=3)
    d.line((M, 1258, W - M, 1258), fill=fg, width=2)
    d.text((M, 1276), HANDLE, font=PX(24), fill=fg)
    f = PM(19)
    room = W - 2 * M - 220
    srcs = list(sources or [])
    def compose():
        parts = (["출처 " + ", ".join(srcs)] if srcs else []) + ([credit] if credit else [])
        return "  |  ".join(parts)
    txt = compose()
    while srcs and d.textlength(txt, font=f) > room:   # 기사 출처를 하나씩 줄임(전체 목록은 캡션에 있음)
        srcs.pop()
        txt = compose()
    while txt and d.textlength(txt, font=f) > room:
        txt = txt[:-2]
    if txt:
        d.text((W - M - d.textlength(txt, font=f), 1282), txt, font=f, fill=sub)


def big_title(d, xy, text, pal, size=120, color=None, width=W - 2 * M):
    size = int(size * {"BH": 1.0, "PX": 0.82, "SR": 0.8}[ST["title"]])
    s = fit_size(d, text, TF, size, width)
    lh = int(s * {"BH": 1.08, "PX": 1.18, "SR": 1.3}[ST["title"]])
    for i, ln in enumerate(text.split("\n")):
        d.text((xy[0], xy[1] + i * lh), ln, font=TF(s), fill=color or pal[2])
    return len(text.split("\n")) * lh


# ---------- 카드별 ----------
def cover_c(c, code, total):
    img, d, pal = canvas("cover")
    ph = c.get("photo")
    if ph:
        p, m = duotone(ph["path"], (690, 690), DUO_DARK, PINK, "circle", cy=ph.get("cy", 0.35), mode=ph.get("mode"))
        img.paste(p, (195, 135), m)
    d = ImageDraw.Draw(img)
    frame(d, pal, code, 1, total, credit=ph and ph["credit"])
    l1, l2 = c["title"]
    s = min(fit_size(d, l1, BH, 170, W - 2 * M), fit_size(d, l2, BH, 170, W - 2 * M))
    ty = 1180 - int(s * 2.06)
    d.text((M, ty - 48), c.get("kicker", ""), font=PX(30), fill=DARK)
    d.text((M - 6, ty), l1, font=BH(s), fill=CREAM)
    d.text((M - 6, ty + int(s * 1.02)), l2, font=BH(s), fill=DARK)
    rich(d, (M, 1192), c["sub"], PB, 30, W - 2 * M, DARK, DARK, gap=1.3, max_h=46, min_size=22)
    if c.get("sticker"):
        st = sticker(c["sticker"], 250, DARK, CREAM)
        img.paste(st, (W - st.width - 40, 470), st)
    return img


def cover_a(c, code, total):
    """매거진형: 사진 전면 + 명조 제목."""
    ph = c.get("photo")
    img = ImageEnhance.Contrast(ImageOps.fit(Image.open(ph["path"]).convert("RGB"), (W, H), Image.LANCZOS,
                                             centering=(0.5, 0.3))).enhance(1.05)
    g = Image.new("L", (1, H))
    for y in range(H):
        t = max(0.0, (y - H * 0.38) / (H * 0.30))
        g.putpixel((0, y), int(240 * min(1, t ** 1.1)))
    img = Image.composite(Image.new("RGB", (W, H), BLACK), img, g.resize((W, H)))
    top = Image.new("L", (1, 240))
    for y in range(240):
        top.putpixel((0, y), int(150 * (1 - y / 240)))
    img.paste(Image.new("RGB", (W, 240)), (0, 0), top.resize((W, 240)))
    d = ImageDraw.Draw(img)
    pal = (BLACK, IVORY, GOLD, (190, 185, 178))
    frame(d, pal, code, 1, total, credit=ph["credit"])
    l1, l2 = c["title"]
    s = min(fit_size(d, l1, SR, 128, W - 2 * M), fit_size(d, l2, SR, 128, W - 2 * M))
    ty = 1095 - int(s * 2.5)
    lab = " ".join(c.get("sticker", [])) if c.get("sticker") else ""
    d.text((M, ty - 62), c.get("kicker", "") + (f"   |   {lab}" if lab else ""), font=PB(29), fill=GOLD)
    d.text((M - 4, ty), l1, font=SR(s), fill=IVORY)
    d.text((M - 4, ty + int(s * 1.25)), l2, font=SR(s), fill=IVORY)
    rich(d, (M, 1130), c["sub"], PM, 32, W - 2 * M, (215, 212, 206), GOLD, gap=1.4, max_h=92, min_size=24)
    return img


def cover_b(c, code, total):
    """리포트형: 종이 배경 + 큰 사진 + 굵은 고딕 제목."""
    img, d, pal = canvas("cover")
    bg, fg, ac, sub = pal
    ph = c.get("photo")
    frame(d, pal, code, 1, total, credit=ph and ph["credit"])
    d.text((M - 4, 128), "01", font=PX(104), fill=ac)
    x = M + 150
    lab = c.get("kicker", "")
    f = PB(26)
    d.rounded_rectangle((x, 160, x + d.textlength(lab, font=f) + 34, 160 + 52), 26, fill=fg)
    d.text((x + 17, 169), lab, font=f, fill=bg)
    if c.get("sticker"):
        t2 = " ".join(c["sticker"])
        x2 = x + d.textlength(lab, font=f) + 50
        d.rounded_rectangle((x2, 160, x2 + d.textlength(t2, font=f) + 34, 212), 26, fill=ac)
        d.text((x2 + 17, 169), t2, font=f, fill=(255, 255, 255))
    l1, l2 = c["title"]
    s = min(fit_size(d, l1, PX, 118, W - 2 * M), fit_size(d, l2, PX, 118, W - 2 * M))
    d.text((M - 4, 250), l1, font=PX(s), fill=fg)
    d.text((M - 4, 250 + int(s * 1.16)), l2, font=PX(s), fill=fg)
    y = 250 + int(s * 2.32) + 30
    if ph:
        p, m = duotone(ph["path"], (W - 2 * M, 1100 - y), None, None, r=30, cy=0.32)
        img.paste(p, (M, y), m)
        d = ImageDraw.Draw(img)
    rich(d, (M, 1130), c["sub"], PB, 34, W - 2 * M, fg, ac, gap=1.42, max_h=110, min_size=24)
    return img


def cover(c, code, total):
    return {"A": cover_a, "B": cover_b, "C": cover_c}[ST["brand_key"]](c, code, total)


def profile(c, code, page, total):
    img, d, pal = canvas("profile")
    bg, fg, ac, sub = pal
    frame(d, pal, code, page, total, c.get("sources"), c.get("photo", {}).get("credit"))
    h = big_title(d, (M - 4, 150), c["title"], pal, 128)
    y = 150 + h + 30
    ph = c.get("photo")
    if ph:
        d = put_photo(img, {**ph, "cy": 0.22} if is_portrait(ph) else ph, (M, y), (W - 2 * M, 430))
        y += 430 + 20
    rows = c["rows"]
    rh = (1230 - y) // len(rows)
    for k, v in rows:
        d.line((M, y, W - M, y), fill=tuple((a + b) // 2 for a, b in zip(bg, fg)) if ST["photo"] == "color" else (225, 205, 190), width=1 if ST["photo"] == "color" else 2)
        d.text((M, y + (rh - 30) // 2), k, font=PB(26), fill=ac)
        vs = 36
        while d.textlength(v, font=PX(vs)) > W - 2 * M - 210 and vs > 24:
            vs -= 1
        d.text((M + 210, y + (rh - vs) // 2 - 4), v, font=PX(vs), fill=fg)
        y += rh
    return img


def story(c, code, page, total):
    img, d, pal = canvas("story")
    bg, fg, ac, sub = pal
    ph = c.get("photo")
    frame(d, pal, code, page, total, c.get("sources"), ph and ph["credit"])
    ty, circle = 150, False
    if ph and is_portrait(ph):                     # 세로 인물 사진 → 오른쪽 위 동그라미
        circle = True
        d = put_photo(img, {**ph, "cy": 0.25}, (W - M - 270, 126), (270, 270), "circle")
    elif ph:
        d = put_photo(img, ph, (M, 132), (W - 2 * M, 380))
        ty = 540
    h = big_title(d, (M - 4, ty), c["title"], pal, 128 if not ph or circle else 96,
                  width=W - 2 * M - 300 if circle else W - 2 * M)
    y = max(ty + h + (40 if not ph or circle else 26), 430 if circle else 0)
    note = c.get("note")
    note_h = 0
    if note:
        nf = PB(33)
        note_h = len(rich_lines(d, note["text"], nf, W - 2 * M - 64)) * int(33 * 1.45) + 96
    avail = 1225 - note_h - 40 - y
    size = 46 if (not ph or circle) else 42
    while size > 25:
        tot = sum(len(rich_lines(d, p, PM(size), W - 2 * M)) * int(size * 1.5) + 22 for p in c["body"])
        if tot <= avail:
            break
        size -= 1
    if (not ph or circle) and tot < avail:          # 남는 공간은 제목 아래 조금만(가운데로 띄우지 않음)
        y += min(60, (avail - tot) // 4)
    for para in c["body"]:
        hh, _ = rich(d, (M, y), para, PM, size, W - 2 * M, fg, ac, gap=1.5)
        y += hh + 22
    if note:
        ny = min(1230 - note_h, y + 36)
        b_bg, b_lab, b_fg = ST["box_a"]
        d.rounded_rectangle((M, ny, W - M, ny + note_h), 26, fill=b_bg)
        d.text((M + 32, ny + 26), note["label"], font=PX(26), fill=b_lab)
        rich(d, (M + 32, ny + 68), note["text"], PB, 33, W - 2 * M - 64, b_fg, b_lab, gap=1.45)
    return img


def numbers(c, code, page, total):
    img, d, pal = canvas("numbers")
    ph = c.get("photo")
    frame(d, pal, code, page, total, c.get("sources"), ph and ph["credit"])
    h = big_title(d, (M - 4, 150), c["title"], pal, 128, color=ST["numbers_title"])
    y0 = 150 + h + 30
    if ph:
        d = put_photo(img, ph, (M, y0), (W - 2 * M, 330))
        y0 += 330 + 26
    items = c["items"][:4]
    gap = 28
    tw = (W - 2 * M - gap) // 2
    th = (1225 - y0 - gap) // 2
    for i, it in enumerate(items):
        x = M + (i % 2) * (tw + gap)
        y = y0 + (i // 2) * (th + gap)
        t_bg, fg = ST["tiles"][0 if i in (0, 3) else 1]
        d.rounded_rectangle((x, y, x + tw, y + th), 30, fill=t_bg)
        vs = fit_size(d, it["value"], TF, int(110 * {"BH": 1, "PX": 0.95, "SR": 0.85}[ST["title"]]), tw - 60)
        vs = min(vs, int(th * 0.36))
        lab_h = len(rich_lines(d, it["label"], PB(31), tw - 60)) * int(31 * 1.35)
        top = y + max(28, (th - (int(vs * 1.25) + 24 + lab_h)) // 2)   # 타일 안에서 세로 가운데
        d.text((x + 30, top), it["value"], font=TF(vs), fill=WINE if (ST["brand_key"] == "A" and sum(t_bg) > 600) else ST["tile_num"])
        ly = min(top + int(vs * 1.25) + 24, y + th - 108)
        rich(d, (x + 32, ly), it["label"], PB, 31, tw - 60, fg, fg, gap=1.35, max_h=90)
    return img


def timeline(c, code, page, total):
    img, d, pal = canvas("timeline")
    bg, fg, ac, sub = pal
    ph = c.get("photo")
    frame(d, pal, code, page, total, c.get("sources"), ph and ph["credit"])
    if ph:
        d = put_photo(img, ph, (W - M - 270, 126), (270, 270), "circle")
    h = big_title(d, (M - 4, 150), c["title"], pal, 128, width=W - 2 * M - 300 if ph else W - 2 * M)
    y = max(150 + h + 40, 420 if ph else 0)
    items = c["items"]
    rh = (1225 - y) // len(items)
    lx = M + max(150, int(max(d.textlength(it["date"], font=PX(34)) for it in items)) + 40)
    d.line((lx, y + 18, lx, y + rh * (len(items) - 1) + 18), fill=fg, width=4 if ST["photo"] == "duo" else 2)
    for i, it in enumerate(items):
        last = i == len(items) - 1
        d.text((M, y + 2), it["date"], font=PX(34), fill=ac)
        r = 14 if last else 10
        d.ellipse((lx - r, y + 18 - r, lx + r, y + 18 + r), fill=ac if last else fg)
        rich(d, (lx + 36, y), it["text"], PB if last else PM, 33, W - M - lx - 36, fg, ac, gap=1.35,
             max_h=rh - 8, min_size=22)
        y += rh
    return img


def debate(c, code, page, total):
    img, d, pal = canvas("debate")
    bg, fg, ac, sub = pal
    ph = c.get("photo")
    frame(d, pal, code, page, total, c.get("sources"), ph and ph["credit"])
    circle = bool(ph) and is_portrait(ph)
    if circle:
        d = put_photo(img, {**ph, "cy": 0.25}, (W - M - 230, 126), (230, 230), "circle")
    h = big_title(d, (M - 4, 150), c["title"], pal, 128, width=W - 2 * M - 260 if circle else W - 2 * M)
    y = max(150 + h + 30, 386 if circle else 0)
    if ph and not circle:
        d = put_photo(img, ph, (M, y), (W - 2 * M, 300))
        y += 300 + 28
    hh, _ = rich(d, (M, y), c["lead"], PB, 36 if ph else 40, W - 2 * M, fg, ac, gap=1.5)
    y += hh + 34
    fs = 28 if ph else 31
    foot_h = len(rich_lines(d, c["foot"], PM(fs), W - 2 * M - 40)) * int(fs * 1.5) + 44
    bw = (W - 2 * M - 24) // 2
    ps0 = 31 if ph else 36
    need = 0
    for side in (c["left"], c["right"]):
        hh0 = 84 + sum(len(rich_lines(d, t, PB(ps0), bw - 102)) * int(ps0 * 1.38) + 18 for t in side["points"]) + 30
        need = max(need, hh0)
    avail = 1225 - foot_h - 24 - y
    box_h = min(avail, need + max(0, avail - need) // 3)   # 남는 공간은 박스와 아래 여백에 나눔
    for i, side in enumerate((c["left"], c["right"])):
        x = M + i * (bw + 24)
        bgc, labc, fgc = ST["box_a"] if i == 0 else ST["box_b"]
        d.rounded_rectangle((x, y, x + bw, y + box_h), 28, fill=bgc)
        d.text((x + 30, y + 26), side["label"], font=PX(33), fill=labc)
        yy = y + 84
        for pnt in side["points"]:
            ps = 31 if ph else 36
            d.text((x + 30, yy), "—", font=PB(ps), fill=fgc)
            hh, _ = rich(d, (x + 72, yy), pnt, PB, ps, bw - 102, fgc, fgc, gap=1.38)
            yy += hh + 18
    fy = 1225 - foot_h
    d.line((M, fy, W - M, fy), fill=sub, width=1)
    rich(d, (M, fy + 22), c["foot"], PM, fs, W - 2 * M - 40, sub, fg, gap=1.5)
    return img


def outro(c, code, page, total, photo=None):
    img, d, pal = canvas("outro")
    ph = c.get("photo")
    frame(d, pal, code, page, total, credit=ph and ph["credit"])
    op = c.get("opinion")
    if ph:
        d = put_photo(img, ph, (W - M - 280, 150), (280, 280), "circle")
    big = int((250 if op else (290 if ph else 330)) * {"BH": 1, "PX": 0.95, "SR": 0.8}[ST["title"]])
    d.text((M - 8, 120), c["big"], font=TF(big), fill=ST["big"])
    y = 120 + int(big * 1.25)
    ts = int((76 if op else 88) * {"BH": 1, "PX": 0.92, "SR": 0.82}[ST["title"]])
    for i, ln in enumerate(c["title"].split("\n")):
        d.text((M, y + i * int(ts * 1.09)), ln, font=TF(ts), fill=ST["outro_title"])
    y += int(ts * 1.09) * len(c["title"].split("\n")) + 20
    hh, _ = rich(d, (M, y), c["body"], PB, 32 if op else 36, W - 2 * M, ST["outro_text"], ST["big"], gap=1.45,
                 max_h=150, min_size=24)
    y += hh + 26
    if op:   # 계정의 의견은 여기(한줄평 상자)에만
        f = PB(34)
        lines = rich_lines(d, op, f, W - 2 * M - 64)
        bh = len(lines) * int(34 * 1.42) + 96
        d.rounded_rectangle((M, y, W - M, y + bh), 26, fill=DARK)
        d.text((M + 32, y + 24), OPINION_LABEL, font=PX(26), fill=RED)
        rich(d, (M + 32, y + 66), op, PB, 34, W - 2 * M - 64, CREAM, RED, gap=1.42)
        y += bh + 26
    d.rounded_rectangle((M, y, W - M, y + 4), 2, fill=ST["outro_text"])
    y += 24
    d.text((M, y), "출처", font=PX(24), fill=ST["outro_text"])
    rich(d, (M + 80, y), " · ".join(c["sources"]), PM, 26, W - 2 * M - 80, pal[3], pal[3], gap=1.45,
         max_h=1110 - y, min_size=20)
    d.text((M, 1130), CTA[0], font=PX(38), fill=ST["outro_cta"])
    d.text((M, 1188), CTA[1], font=PB(28), fill=ST["outro_text"])
    d.text((M, 1226), NOTE, font=PM(19), fill=pal[3])
    return img


def render(post_dir, style="C", out_dir=None, channel=None):
    global ST
    if channel:
        set_channel(channel)
    ST = dict(STYLES[style], brand_key=style)
    out_dir = out_dir or post_dir
    os.makedirs(out_dir, exist_ok=True)
    c = json.load(open(os.path.join(post_dir, "content.json"), encoding="utf-8"))
    code, cards = c.get("code", "BUZZ"), c["cards"]
    total = len(cards)
    fn = {"profile": profile, "story": story, "numbers": numbers, "timeline": timeline, "debate": debate}
    pages = []
    for i, card in enumerate(cards, 1):
        t = card["type"]
        if t == "cover":
            pages.append(cover(card, code, total))
        elif t == "outro":
            pages.append(outro(card, code, i, total, cards[0].get("photo")))
        else:
            pages.append(fn[t](card, code, i, total))
    out = []
    for i, p in enumerate(pages, 1):
        f = os.path.join(out_dir, f"{i:02d}.jpg")
        p.save(f, quality=90, optimize=True, progressive=True)
        out.append(f)
    return out


if __name__ == "__main__":
    print(render(sys.argv[1], *(sys.argv[2:3] or ["C"]), *(sys.argv[3:4] or [None])))
