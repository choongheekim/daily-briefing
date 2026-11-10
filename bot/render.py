"""카드뉴스 이미지(1080x1350, 4:5) 생성."""
import glob
import os
import re
from datetime import datetime, timedelta, timezone

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350
BG = (14, 14, 18)
FG = (245, 245, 245)
SUB = (170, 170, 180)
ACCENT = (230, 32, 45)      # 자극적인 레드
YELLOW = (255, 214, 0)
ACCOUNT = os.getenv("IG_HANDLE", "@daily_politics_kr")
LABEL = "오늘의 정치 핫이슈"


def set_theme(channel: dict):
    """채널별 색·계정명·라벨 적용."""
    global ACCENT, YELLOW, ACCOUNT, LABEL
    ACCENT = tuple(channel.get("accent", ACCENT))
    YELLOW = tuple(channel.get("highlight", YELLOW))
    ACCOUNT = channel.get("handle", ACCOUNT)
    LABEL = channel.get("label", LABEL)
KST = timezone(timedelta(hours=9))


def _font_path(weight: str) -> str:
    """Noto Sans CJK(KR) 찾기. GitHub Actions에서는 fonts-noto-cjk 설치."""
    pats = {
        "black": ["**/NotoSansCJK-Black.ttc", "**/NotoSansCJKkr-Black.otf"],
        "bold": ["**/NotoSansCJK-Bold.ttc", "**/NotoSansCJK-Black.ttc", "**/NotoSansCJKkr-Bold.otf"],
        "regular": ["**/NotoSansCJK-Regular.ttc", "**/NotoSansCJKkr-Regular.otf"],
    }[weight]
    for root in ["/usr/share/fonts", os.path.expanduser("~/.fonts"), "fonts"]:
        for p in pats:
            hits = glob.glob(os.path.join(root, p), recursive=True)
            if hits:
                return hits[0]
    raise FileNotFoundError("한글 폰트(Noto Sans CJK)를 찾지 못함")


FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts")
BUNDLED = {  # 저장소에 포함된 폰트(OFL) — 없으면 Noto로 대체
    "title": "BlackHanSans-Regular.ttf",   # 제목·숫자: 검은고딕
    "black": "Pretendard-ExtraBold.otf",
    "bold": "Pretendard-Bold.otf",
    "regular": "Pretendard-Medium.otf",
}


# 뉴스 제목에 자주 쓰는 한자 약칭 → 한글 (새 폰트엔 한자가 없음)
HANJA = {"李": "이", "尹": "윤", "文": "문", "朴": "박", "金": "김", "韓": "한", "靑": "청", "與": "여",
         "野": "야", "北": "북", "南": "남", "美": "미", "中": "중", "日": "일", "英": "영", "佛": "불",
         "獨": "독", "露": "러", "軍": "군", "檢": "검", "警": "경", "法": "법", "黨": "당", "對": "대",
         "前": "전", "新": "신", "親": "친", "反": "반", "非": "비", "現": "현", "故": "고", "總": "총",
         "稅": "세", "株": "주", "銀": "은", "核": "핵", "兆": "조", "億": "억", "萬": "만"}
_COVER: set | None = None


def _covered() -> set:
    """번들 폰트 모두에 들어 있는 글자 집합."""
    global _COVER
    if _COVER is None:
        try:
            from fontTools.ttLib import TTFont
            sets = [set(TTFont(os.path.join(FONT_DIR, f)).getBestCmap()) for k, f in BUNDLED.items()
                    if k != "title" and os.path.isfile(os.path.join(FONT_DIR, f))]
            _COVER = set.intersection(*sets) if sets else set()
        except Exception:
            _COVER = set()
    return _COVER


def clean_text(t: str) -> str:
    """한자 약칭을 한글로 바꾸고, 폰트에 없는 글자는 제거."""
    if not t:
        return t
    t = re.sub(r"([李尹文朴])(?=대통령|전 대통령|대표|후보|정부)", lambda m: HANJA[m.group(1)] + " ", t)
    t = re.sub(r"李(?!\s*(?:전\s*)?대통령)(?=[\s\"“'‘,]|$)", "이 대통령", t)   # 단독 '李' = 이 대통령
    t = "".join(HANJA.get(c, c) for c in t)
    cov = _covered()
    if not cov:
        return t
    return "".join(c for c in t if ord(c) in cov or c in " \n")


TITLE_SUB = {"·": ", ", "ㆍ": ", ", "‧": ", ", "…": "...", "—": "-", "–": "-", "→": "-", "※": "", "▶": "", "•": ""}
_TCOVER: set | None = None


def title_text(t: str) -> str:
    """제목 폰트(검은고딕)에 없는 기호를 비슷한 기호로 바꾸고, 그래도 없는 글자는 제거."""
    global _TCOVER
    t = re.sub(r"(?<=\d)[·ㆍ‧](?=\d)", ".", t)          # 12·3 → 12.3
    t = re.sub(r"(?<![가-힣])([가-힣])[·ㆍ‧]([가-힣])(?![가-힣])", r"\1\2", t)  # 당·청 → 당청
    t = "".join(TITLE_SUB.get(c, c) for c in t).replace(",  ", ", ")
    if _TCOVER is None:
        try:
            from fontTools.ttLib import TTFont
            _TCOVER = set(TTFont(os.path.join(FONT_DIR, BUNDLED["title"])).getBestCmap())
        except Exception:
            _TCOVER = set()
    return "".join(c for c in t if not _TCOVER or ord(c) in _TCOVER or c == " ")


def sanitize(content: dict) -> dict:
    for k in ("cover_title", "reel_hook", "caption_hook"):
        if content.get(k):
            content[k] = clean_text(content[k])
    for st in content.get("stories", []):
        for k in ("headline", "comment", "reel_comment", "person", "tag"):
            if st.get(k):
                st[k] = clean_text(st[k])
        st["points"] = [clean_text(p) for p in st.get("points", [])]
    return content


def font(size: int, weight: str = "bold") -> ImageFont.FreeTypeFont:
    p = os.path.join(FONT_DIR, BUNDLED.get(weight, ""))
    if os.path.isfile(p):
        return ImageFont.truetype(p, size)
    path = _font_path("black" if weight == "title" else weight)
    idx = 1 if path.endswith(".ttc") else 0
    return ImageFont.truetype(path, size, index=idx)


def wrap(draw, text, fnt, max_w):
    """한글은 글자 단위, 공백 우선으로 줄바꿈."""
    lines, cur = [], ""
    for word in text.split(" "):
        trial = (cur + " " + word).strip()
        if draw.textlength(trial, font=fnt) <= max_w:
            cur = trial
            continue
        if cur:
            lines.append(cur)
        cur = ""
        for ch in word:  # 단어 자체가 너무 길면 글자 단위
            if draw.textlength(cur + ch, font=fnt) <= max_w:
                cur += ch
            else:
                lines.append(cur)
                cur = ch
    if cur:
        lines.append(cur)
    return lines


def title_draw(d, xy, text, fnt, fill):
    """제목용 외곽선+그림자. 폰트 외곽선 기능(버전·OS별로 일부 글자에서 실패)을 쓰지 않고
    글자 모양을 직접 부풀려(dilate) 테두리를 만든다 → 어떤 PC에서도 동일."""
    from PIL import ImageFilter
    x, y = xy
    sw = max(4, fnt.size // 18)
    pad = sw * 2 + 10
    l, t, r, btm = d.textbbox((0, 0), text, font=fnt)
    w, h = r - l + pad * 2, btm - t + pad * 2
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).text((pad - l, pad - t), text, font=fnt, fill=255)
    k = sw * 2 + 1
    outline = mask.filter(ImageFilter.MaxFilter(k if k % 2 else k + 1))
    img = d._image
    ox, oy = x + l - pad, y + t - pad
    black = Image.new("RGB", (w, h), (0, 0, 0))
    img.paste(black, (ox + 4, oy + 6), outline)   # 그림자
    img.paste(black, (ox, oy), outline)           # 테두리
    img.paste(Image.new("RGB", (w, h), fill), (ox, oy), mask)  # 글자


def _base():
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 14], fill=ACCENT)
    return img, d


def _footer(d, page, total):
    d.text((70, H - 90), ACCOUNT, font=font(30, "regular"), fill=SUB)
    t = f"{page} / {total}"
    f = font(30, "regular")
    d.text((W - 70 - d.textlength(t, font=f), H - 90), t, font=f, fill=SUB)


def _background(img, photo):
    """전면 배경 사진. photo=(경로, 출처, 'person'|'scene').
    person: 얼굴이 보이도록 위쪽은 밝게, 글자 영역은 어둡게
    scene : 전체를 어둡게 깔아 글자 가독성 확보(사진은 은은하게 보임)"""
    path, credit, kind = photo
    ph = Image.open(path).convert("RGB")
    scale = max(W / ph.width, H / ph.height)
    ph = ph.resize((int(ph.width * scale) + 1, int(ph.height * scale) + 1), Image.LANCZOS)
    x = (ph.width - W) // 2
    y = int((ph.height - H) * (0.2 if kind == "person" else 0.35 if kind == "event" else 0.5))
    img.paste(ph.crop((x, y, x + W, y + H)), (0, 0))
    grad = Image.new("L", (1, H))
    for i in range(H):
        t = i / H
        if kind in ("person", "event"):
            a = 90 if t < 0.12 else 30 if t < 0.30 else int(30 + 200 * min(1, (t - 0.30) / 0.25))
        else:
            a = int(150 + 75 * t)
        grad.putpixel((0, i), min(a, 232))
    img.paste(Image.new("RGB", (W, H), BG), (0, 0), grad.resize((W, H)))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 14], fill=ACCENT)
    if credit:
        f = font(20, "regular")
        d.text((W - 30 - d.textlength(credit, font=f), 28), credit, font=f, fill=(225, 225, 230), stroke_width=1, stroke_fill=(0, 0, 0))


def cover(title: str, stories: list[dict], total: int, photo=None) -> Image.Image:
    img, d = _base()
    if photo:
        _background(img, photo)
        d = ImageDraw.Draw(img)
    person = bool(photo) and photo[2] == "person"
    photo_layout = bool(photo) and photo[2] in ("person", "event")
    now = datetime.now(KST)
    wd = "월화수목금토일"[now.weekday()]
    d.text((70, 90), f"{now:%Y.%m.%d} ({wd})", font=font(40, "regular"), fill=FG if photo else SUB)

    lab_f = font(44, "title")
    lab = LABEL
    lw = d.textlength(lab, font=lab_f)
    d.rectangle([70, 170, 70 + lw + 40, 250], fill=ACCENT)
    d.text((90, 178), lab, font=lab_f, fill=FG)

    tf = font(108 if photo_layout else 112, "title")
    lines = wrap(d, title_text(title), tf, W - 140)[:3]
    y = (850 - len(lines) * 122) if photo_layout else 330
    for line in lines:
        title_draw(d, (70, y), line, tf, YELLOW)
        y += 122 if photo_layout else 130

    y = max(y + 40, 880)
    d.line([70, y, W - 70, y], fill=(60, 60, 70), width=3)
    y += 34
    lf = font(36, "bold")
    for i, s in enumerate(stories, 1):
        line = wrap(d, s["headline"], lf, W - 220)[0]
        d.text((70, y), f"{i:02d}", font=lf, fill=ACCENT)
        d.text((150, y), line, font=lf, fill=FG)
        y += 56
    _footer(d, 1, total)
    return img


def story_card(s: dict, num: int, page: int, total: int, photo=None) -> Image.Image:
    img, d = _base()
    if photo:
        _background(img, photo)
        d = ImageDraw.Draw(img)
    person = bool(photo) and photo[2] == "person"
    photo_layout = bool(photo) and photo[2] in ("person", "event")
    nf_ = font(130, "title")
    d.text((70, 60), f"{num:02d}", font=nf_, fill=ACCENT)
    tag_f = font(36, "bold")
    tag = s.get("tag", "정치")
    tw = d.textlength(tag, font=tag_f)
    tx = int(70 + d.textlength(f"{num:02d}", font=nf_) + 30)
    d.rounded_rectangle([tx, 120, tx + tw + 44, 180], radius=30,
                        fill=(0, 0, 0) if photo else None, outline=FG, width=3)
    d.text((tx + 22, 124), tag, font=tag_f, fill=FG)
    if person and s.get("person"):
        nf = font(34, "bold")
        d.text((70, 372), s["person"], font=nf, fill=FG, stroke_width=3, stroke_fill=(0, 0, 0))

    hf = font(86 if photo_layout else 92, "title")
    lines = wrap(d, title_text(s["headline"]), hf, W - 140)[: 2 if photo_layout else 3]
    y = 425 if photo_layout else 270
    for line in lines:
        title_draw(d, (70, y), line, hf, YELLOW)
        y += 104 if photo_layout else 110

    y += 30
    d.rectangle([70, y, 190, y + 10], fill=ACCENT)
    y += 50
    # ── 한줄평: 글씨 크기를 줄여가며 최대 3줄 안에 전부 들어가게
    cm = s.get("comment") or ""
    cmw = W - 60 - 98 - 40
    c_lines, c_size = [], 38
    if cm:
        for c_size in (38, 35, 32, 29):
            c_lines = wrap(d, cm, font(c_size, "black"), cmw)
            if len(c_lines) <= (2 if c_size >= 35 else 3):
                break
        c_lines = c_lines[:3]
    c_lh = int(c_size * 1.42)
    bh = 78 + len(c_lines) * c_lh if cm else 0
    limit = (H - 185 - bh - 24) if cm else H - 190

    # ── 핵심 사실 3줄: 전부 들어가는 가장 큰 글씨 크기 선택
    pts = s["points"][:3]
    sizes = (42, 39, 36, 33) if photo_layout else (46, 42, 39, 36)
    for psz in sizes:
        pf = font(psz, "bold")
        lh = int(psz * 1.38)
        gap = int(psz * 0.6)
        wrapped = [wrap(d, p, pf, W - 200)[:2] for p in pts]
        need = sum(len(w) * lh + gap for w in wrapped)
        if y + need <= limit:
            break
    for lines in wrapped:
        if y + len(lines) * lh > limit:
            break
        d.ellipse([74, y + int(lh * 0.3), 94, y + int(lh * 0.3) + 20], fill=ACCENT)
        for line in lines:
            d.text((120, y), line, font=pf, fill=FG, stroke_width=1, stroke_fill=(0, 0, 0))
            y += lh
        y += gap

    if cm:
        cf = font(c_size, "black")
        by = H - 185 - bh
        d.rounded_rectangle([60, by, W - 60, by + bh], radius=16,
                            fill=tuple(int(c * 0.22 + 20) for c in ACCENT))
        d.rectangle([60, by, 72, by + bh], fill=ACCENT)
        chip_f = font(28, "black")
        chip = "한줄평"
        cw = d.textlength(chip, font=chip_f)
        d.rounded_rectangle([96, by + 18, 96 + cw + 26, by + 60], radius=10, fill=ACCENT)
        d.text((109, by + 21), chip, font=chip_f, fill=FG)
        ty = by + 72
        for ln in c_lines:
            d.text((98, ty), ln, font=cf, fill=FG)
            ty += c_lh

    src = "출처: " + ", ".join(s.get("sources", [])[:4])
    d.text((70, H - 150), src, font=font(28, "regular"), fill=SUB)
    _footer(d, page, total)
    return img


def outro(total: int, photo=None) -> Image.Image:
    img, d = _base()
    if photo:
        _background(img, photo)
        d = ImageDraw.Draw(img)
    f1 = font(100, "title")
    y = 430
    for line in ["매일 아침", "정치 핫이슈", "5개만 콕"]:
        title_draw(d, (70, y), line, f1, YELLOW if line == "정치 핫이슈" else FG)
        y += 120
    d.text((70, y + 40), f"팔로우 {ACCOUNT}", font=font(54, "black"), fill=ACCENT, stroke_width=3, stroke_fill=(255, 255, 255))
    note = "※ 언론 보도를 AI가 요약했습니다. 한줄평은 이 계정의 의견입니다. 원문은 캡션의 출처를 확인하세요."
    nf = font(28, "regular")
    yy = H - 220
    for line in wrap(d, note, nf, W - 140):
        d.text((70, yy), line, font=nf, fill=SUB)
        yy += 42
    _footer(d, total, total)
    return img


def pick_photo(person, tag, salt, queries=None):
    """배경 사진 선택: ① 정부 현장 사진 → ② 인물 사진 → ③ 분야별 장소 → ④ 기본."""
    from bot.backgrounds import get_background
    from bot.event_photos import get_event_photo
    from bot.photos import get_photo
    e = get_event_photo(queries or [], tag)
    if e:
        return (*e, "event")
    p = get_photo(person)
    if p:
        return (*p, "person")
    b = get_background(tag, salt)
    return (*b, "scene") if b else None


def render_all(content: dict, out_dir: str) -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    content = sanitize(content)
    stories = content["stories"]
    total = len(stories) + 2
    pick = pick_photo

    top_tag = stories[0].get("tag") if stories else None
    top_q = stories[0].get("photo_queries") if stories else None
    imgs = [cover(content["cover_title"], stories, total, pick(content.get("cover_person"), top_tag, 0, top_q))]
    imgs += [story_card(s, i, i + 1, total, pick(s.get("person"), s.get("tag"), i, s.get("photo_queries")))
             for i, s in enumerate(stories, 1)]
    imgs.append(outro(total, pick(None, None, 7)))
    paths = []
    for i, im in enumerate(imgs, 1):
        p = os.path.join(out_dir, f"{i:02d}.jpg")
        im.save(p, "JPEG", quality=92)
        paths.append(p)
    return paths
