"""분위기·장소 배경 사진: Openverse (워드프레스 재단의 무료 CC 이미지 검색, 키 필요 없음).

위키미디어·Flickr 등 자유 라이선스 사진을 라이선스 정보와 함께 돌려준다.
- 상업 이용·변형 가능한 라이선스만(CC0, 퍼블릭도메인, CC BY, CC BY-SA), BY-SA는 후순위
- 가로 1600px 이상만, 사람이 주인공인 사진(제목·태그에 man/woman/portrait 등)은 제외
- 위키미디어 원본은 표준 크기(1920px) 썸네일로 받음(그 외 크기는 429 차단)
"""
import os
import re
import time
from urllib.parse import quote, unquote

import requests

API = "https://api.openverse.org/v1/images/"
DIR = "openverse_cache"
UA = {"User-Agent": f"insta-news-bot/1.0 (https://github.com/{os.getenv('GITHUB_REPOSITORY', 'choongheekim/daily-briefing')})"}
PEOPLE = re.compile(r"\b(man|men|woman|women|person|people|girl|boy|child|portrait|face|couple|crowd|"
                    r"selfie|model|prosecutor|president|minister|senator|politician|judge \w+ \w+)\b", re.I)
LIC = {"cc0": "CC0", "pdm": "Public domain", "by": "CC BY", "by-sa": "CC BY-SA"}
_USED: set[str] = set()
_CACHE: dict[str, list] = {}


def _wiki_thumb(url: str, width: int) -> str:
    """upload.wikimedia.org 원본 주소 → 1920px 표준 썸네일 주소."""
    m = re.match(r"https://upload\.wikimedia\.org/wikipedia/commons/(\w)/(\w\w)/(.+)$", url)
    if not m or width <= 1920:
        return url
    a, ab, name = m.groups()
    return f"https://upload.wikimedia.org/wikipedia/commons/thumb/{a}/{ab}/{name}/1920px-{quote(unquote(name))}"


def _search(query: str) -> list[dict]:
    if query in _CACHE:
        return _CACHE[query]
    try:
        r = requests.get(API, headers=UA, timeout=30, params={
            "q": query, "license": "cc0,pdm,by,by-sa", "size": "large", "page_size": 20,
            "source": "wikimedia",          # 원본 화질·라이선스 정보가 확실한 위키미디어만
            "mature": "false"})
        r.raise_for_status()
        res = r.json().get("results", [])
    except Exception as e:
        print(f"[openverse] 검색 실패({query}): {e}")
        res = []
    _CACHE[query] = res
    return res


def get_scene(query: str | None) -> tuple[str, str] | None:
    """검색어가 길어 결과가 없으면 앞 두 단어로 다시 찾는다."""
    if not query:
        return None
    words = query.split()
    for q in dict.fromkeys([query, " ".join(words[:2]), words[0]]):
        r = _get(q)
        if r:
            return r
    return None


def _get(query: str) -> tuple[str, str] | None:
    hits = [h for h in _search(query)
            if (h.get("width") or 0) >= 1600 and h.get("license") in LIC and h["id"] not in _USED
            and not PEOPLE.search(" ".join([h.get("title") or ""] + [t.get("name", "") for t in h.get("tags") or []]))]
    hits.sort(key=lambda h: h["license"] == "by-sa")      # BY-SA는 뒤로
    for h in hits[:6]:
        os.makedirs(DIR, exist_ok=True)
        path = os.path.join(DIR, f"{h['id']}.jpg")
        if not os.path.exists(path):
            img = None
            for wait in (0, 6, 20):          # 위키미디어 429(접속 제한)면 잠깐 쉬었다 재시도
                time.sleep(wait)
                try:
                    img = requests.get(_wiki_thumb(h["url"], h.get("width") or 0), headers=UA, timeout=60)
                except requests.RequestException:
                    img = None
                    continue
                if img.status_code != 429:
                    break
            if img is None:
                continue
            if img.status_code != 200 or not img.headers.get("content-type", "").startswith("image/jpeg"):
                continue
            open(path, "wb").write(img.content)
        try:
            from PIL import Image
            with Image.open(path) as im:
                if im.width < 1600:           # 실제 받은 사진이 작으면 버림
                    continue
        except Exception:
            continue
        _USED.add(h["id"])
        lic = LIC[h["license"]] + (f" {h['license_version']}" if h["license"] in ("by", "by-sa") and h.get("license_version") else "")
        creator = re.sub(r"\s+", " ", (h.get("creator") or ""))[:28]
        if not creator or "unknown author" in creator.lower():
            creator = "작자 미상"
        src = {"wikimedia": "Wikimedia Commons", "flickr": "Flickr"}.get(h.get("source"), h.get("source", ""))
        print(f"[openverse] '{query}' → {(h.get('title') or '')[:40]} ({lic})")
        return path, f"사진: {creator} / {lic} / {src}"
    return None
