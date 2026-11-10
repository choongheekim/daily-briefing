"""이슈 분야별 배경 사진 (위키미디어 공용, 자유 라이선스만).

인물 사진이 없을 때 쓰는 장소 사진. backgrounds/ 에 **검수된 세트가 기본 포함**돼 있고
(manifest.json 에 저작자·라이선스 기록), 분야마다 날짜별로 돌려 쓴다.
사진을 추가하려면 backgrounds/에 넣고 manifest.json 에 항목을 추가하면 된다.
AUTO_BG=1 이면 세트에 없는 분야를 위키미디어 카테고리에서 자동 수집(품질 들쭉날쭉 → 비추천).
"""
import json
import os
import re
from datetime import date

from bot.photos import ALLOWED, _api, UA, clean_artist, html, requests

DIR = "backgrounds"
MANIFEST = os.path.join(DIR, "manifest.json")
PER_TOPIC = 5
_USED: set[str] = set()   # 한 게시물 안에서 같은 배경 반복 방지

# 태그 → 위키미디어 공용 카테고리 (장소·건물 위주. 원하면 수정)
TOPICS = {
    "국회": "National Assembly Building of South Korea",
    "대통령실": "Cheongwadae",
    "사법": "Supreme Court of Korea",
    "외교": "Government Complex Seoul",
    "안보": "War Memorial of Korea",
    "경제": "Yeouido",
    "부동산": "Apartment buildings in Seoul",
    "예산": "Government Complex Sejong",
    "지방": "Seoul City Hall",
    "선거": "Gwanghwamun",
    "기본": "Gwanghwamun",
}
# 인물·행사 사진은 배경에서 제외(초상권·저작권 안내문 이슈 회피)
EXCLUDE = re.compile(r"president|대통령|minister|장관|meet|ceremony|visit|prime|summit|logo|map|plan|interior|"
                     r"내부|회담|기념식|portrait|with ", re.I)

TAG_MAP = {  # AI가 붙인 태그 → 위 분야
    "국회": "국회", "여당": "국회", "야당": "국회", "정당": "국회",
    "대통령실": "대통령실", "청와대": "대통령실", "정부": "대통령실",
    "사법": "사법", "법무부": "사법", "검찰": "사법", "법원": "사법", "특검": "사법",
    "외교": "외교", "통일": "외교", "북한": "안보", "안보": "안보", "국방": "안보",
    "경제": "경제", "부동산": "부동산", "예산": "예산", "재정": "예산",
    "지방": "지방", "선거": "선거",
}


def _load():
    if os.path.exists(MANIFEST):
        return json.load(open(MANIFEST, encoding="utf-8"))
    return {}


def _collect(topic: str) -> list[dict]:
    res = _api("https://commons.wikimedia.org/w/api.php", {
        "action": "query", "generator": "categorymembers", "gcmtitle": f"Category:{TOPICS[topic]}",
        "gcmtype": "file", "gcmlimit": 60,
        "prop": "imageinfo", "iiprop": "url|extmetadata|size|mime", "iiurlwidth": 1400})
    pages = list(res.get("query", {}).get("pages", {}).values())
    os.makedirs(DIR, exist_ok=True)
    good = []
    for p in pages:
        ii = p.get("imageinfo", [{}])[0]
        meta = ii.get("extmetadata", {})
        lic = meta.get("LicenseShortName", {}).get("value", "")
        desc = meta.get("ImageDescription", {}).get("value", "")
        w, h = ii.get("width", 0), ii.get("height", 1)
        if (not ALLOWED.match(lic) or ii.get("mime") != "image/jpeg" or w < 1200
                or not 0.6 <= w / h <= 2.2 or EXCLUDE.search(p["title"] + " " + desc)):
            continue
        good.append((p, ii, meta, lic))
    # 골고루: 후보를 균등 간격으로 PER_TOPIC장 선택
    step = max(1, len(good) // PER_TOPIC)
    out = []
    for p, ii, meta, lic in good[::step][:PER_TOPIC]:
        artist = re.sub(r"<[^>]+>", "", html.unescape(meta.get("Artist", {}).get("value", ""))).strip()
        fn = f"{topic}_{len(out) + 1}.jpg"
        img = requests.get(ii.get("thumburl") or ii["url"], headers=UA, timeout=60)
        if img.status_code != 200:
            continue
        open(os.path.join(DIR, fn), "wb").write(img.content)
        out.append({"file": fn, "credit": f"사진: {clean_artist(artist)} / {lic} / Wikimedia Commons"})
    return out


def get_background(tag: str | None, salt: int = 0) -> tuple[str, str] | None:
    topic = TAG_MAP.get((tag or "").strip(), "기본")
    m = _load()
    if topic not in m and os.getenv("AUTO_BG") == "1":
        try:
            m[topic] = _collect(topic)
        except Exception as e:
            print(f"[bg] {topic} 수집 실패: {e}")
            m[topic] = []
        if m[topic]:
            json.dump(m, open(MANIFEST, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    items = [i for i in m.get(topic, []) if os.path.exists(os.path.join(DIR, i["file"]))]
    if not items and topic != "기본":
        return get_background("기본", salt)
    if not items:
        return None
    fresh = [i for i in items if i["file"] not in _USED]
    if not fresh and topic != "기본":
        return get_background("기본", salt)      # 분야 사진을 다 썼으면 기본 배경으로
    pool = fresh or items
    pick = pool[(date.today().toordinal() + salt) % len(pool)]
    _USED.add(pick["file"])
    return os.path.join(DIR, pick["file"]), pick["credit"]
