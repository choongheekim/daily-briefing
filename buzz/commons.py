"""위키미디어 공용에서 '실물 사진' 찾기 — 화제 이름(인물·작품·장소·동물)으로 검색.

- 허용: CC0, Public domain, CC BY, CC BY-SA  (NC·ND·공정이용은 제외)
- 삭제 요청·저작권 위반·허락 없음 표시가 붙은 파일은 제외
- 1920px 이하 표준 썸네일로 받음(원본 직접 받기는 자주 막힘)
- CC BY-SA 사진을 쓰면 게시물 캡션에 같은 조건(CC BY-SA)으로 공유 가능하다고 적어야 함 → share_alike 플래그
"""
import hashlib
import html
import os
import re
import time

import requests

API = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "daily-briefing/1.0 (https://github.com/choongheekim/daily-briefing)"}
CACHE = "image_cache"
BAD_TEMPLATES = re.compile(r"Delete|Deletion|Copyvio|No permission|No source|No license|Speedy|Disputed|Fair use|"
                           r"Non-free|PD-Japan-oldphoto|Watermark|Personality rights warning", re.I)
OK_LICENSE = re.compile(r"^(CC0|Public domain|PD|CC BY(-SA)? [0-9.]+|CC BY(-SA)?|KOGL Type 1|공공누리 ?제?1유형)", re.I)
BAD_LICENSE = re.compile(r"NC|ND|GFDL only|Fair", re.I)


def _api(params, tries=5):
    params = {**params, "format": "json", "formatversion": 2, "maxlag": 5}
    for i in range(tries):
        try:
            r = requests.get(API, headers=UA, params=params, timeout=30)
            if r.status_code == 200 and "error" not in r.json():
                return r.json()
        except (requests.RequestException, ValueError):
            pass
        time.sleep(min(60, 6 * (i + 1)))
    return {}


def _clean(html_text: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html_text or "")).strip())


def _files_for(query: str, limit: int) -> list[str]:
    titles = []
    # ① 같은 이름의 분류(카테고리)가 있으면 그 안의 파일이 가장 정확함
    cats = _api({"action": "query", "list": "search", "srsearch": query, "srnamespace": 14, "srlimit": 3})
    for c in cats.get("query", {}).get("search", [])[:2]:
        mem = _api({"action": "query", "list": "categorymembers", "cmtitle": c["title"], "cmtype": "file",
                    "cmlimit": limit})
        titles += [m["title"] for m in mem.get("query", {}).get("categorymembers", [])]
    # ② 파일 이름·설명 검색
    s = _api({"action": "query", "list": "search", "srsearch": f"{query} filetype:bitmap", "srnamespace": 6,
              "srlimit": limit})
    titles += [x["title"] for x in s.get("query", {}).get("search", [])]
    seen, out = set(), []
    for t in titles:
        if t not in seen and re.search(r"\.(jpe?g|png|webp|tiff?)$", t, re.I):
            seen.add(t)
            out.append(t)
    return out[:limit]


def search(query: str, limit: int = 12, min_side: int = 1000) -> list[dict]:
    """라이선스·경고·해상도 검사를 통과한 후보 목록(다운로드 전)."""
    out = _info(_files_for(query, limit * 2), min_side)
    # 라이선스 우선(CC0·PD·공공누리1·CC BY → CC BY-SA), 그다음 직접 촬영·최근 사진
    out.sort(key=lambda x: (x["share_alike"], not x["own_work"], -int((re.findall(r"\d{4}", x["date"]) or ["0"])[0])))
    return out[:limit]


def from_wikipedia(name: str, limit: int = 4, min_side: int = 600) -> list[dict]:
    """위키백과(한국어→영어) 문서의 대표 사진 + 문서에 실린 사진. 인물·기관과 '확실히 같은 대상'인 사진을 얻는 가장 정확한 방법."""
    titles = []
    for lang in ("ko", "en"):
        try:
            r = requests.get(f"https://{lang}.wikipedia.org/w/api.php", headers=UA, timeout=30, params={
                "action": "query", "titles": name, "redirects": 1, "prop": "pageimages|images",
                "piprop": "name", "imlimit": 30, "format": "json", "formatversion": 2}).json()
        except (requests.RequestException, ValueError):
            continue
        for pg in r.get("query", {}).get("pages", []):
            if pg.get("missing"):
                continue
            if pg.get("pageimage"):
                titles.append("File:" + pg["pageimage"])
            titles += [i["title"].replace("파일:", "File:") for i in pg.get("images", [])]
        if titles:
            break
    titles = [t for t in dict.fromkeys(titles) if re.search(r"\.(jpe?g|png|webp)$", t, re.I)
              and not re.search(r"logo|symbol|flag|emblem|signature|서명|로고|기|map|지도", t, re.I)]
    out = _info(titles[:20], min_side)
    lead = titles[0] if titles else None
    for c in out:
        c["wiki"] = name
        c["lead"] = c["title"] == lead
    out.sort(key=lambda x: (not x["lead"], x["share_alike"]))
    return out[:limit]


def _info(titles, min_side=1000):
    out = []
    for i in range(0, len(titles), 20):
        data = _api({"action": "query", "titles": "|".join(titles[i:i + 20]), "prop": "imageinfo|templates",
                     "iiprop": "url|size|extmetadata", "iiurlwidth": 1920, "tllimit": 100})
        for p in data.get("query", {}).get("pages", []):
            if not p.get("imageinfo"):
                continue
            ii = p["imageinfo"][0]
            m = ii.get("extmetadata", {})
            lic = _clean(m.get("LicenseShortName", {}).get("value"))
            tpl = " ".join(t["title"] for t in p.get("templates", []))
            if not OK_LICENSE.search(lic) or BAD_LICENSE.search(lic) or BAD_TEMPLATES.search(tpl):
                continue
            if max(ii["width"], ii["height"]) < min_side:
                continue
            artist = _clean(m.get("Artist", {}).get("value"))[:60]
            half = len(artist) // 2
            if artist and artist[:half] == artist[half:]:          # "Unknown authorUnknown author" 같은 중복
                artist = artist[:half]
            if not artist or "unknown" in artist.lower():
                artist = "Wikimedia Commons"
            out.append({
                "title": p["title"], "w": ii["width"], "h": ii["height"],
                "thumb": ii.get("thumburl") or ii["url"], "page": ii.get("descriptionurl"),
                "license": lic, "artist": artist,
                "desc": _clean(m.get("ImageDescription", {}).get("value"))[:160],
                "date": _clean(m.get("DateTimeOriginal", {}).get("value"))[:20],
                "own_work": "Own work" in _clean(m.get("Credit", {}).get("value")),
                "share_alike": "SA" in lic.upper(),
                "credit": f"Photo: {artist} / {lic}",
            })
    return out


def download(c: dict) -> str | None:
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, "wm_" + hashlib.md5(c["thumb"].encode()).hexdigest()[:12] + ".jpg")
    if os.path.exists(path):
        return path
    for i in range(6):
        try:
            r = requests.get(c["thumb"], headers=UA, timeout=60)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
                from io import BytesIO
                from PIL import Image
                Image.open(BytesIO(r.content)).convert("RGB").save(path, quality=92)
                return path
        except requests.RequestException:
            pass
        time.sleep(min(60, 7 * (i + 1)))
    return None


if __name__ == "__main__":
    import sys
    for c in search(" ".join(sys.argv[1:]) or "Punch-kun"):
        print(f"{c['w']}x{c['h']} {c['license']:12} {c['artist'][:20]:20} own={c['own_work']} {c['date'][:10]} | {c['title'][:60]}")
