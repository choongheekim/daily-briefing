"""그날 뉴스 현장 사진: 정부 공식 Flickr(코리아넷)에서 최근 행사 사진 검색.

대통령 일정·국무회의·정상회담·정부 행사 등이 매일 올라온다(CC BY-SA 2.0).
언론사·통신사 사진은 저작권 침해라 쓰지 않는다 — 여기서만 '현장 사진'을 가져온다.

필요: FLICKR_API_KEY (무료, https://www.flickr.com/services/apps/create/apply/)
"""
import os
import time

import requests

API = "https://api.flickr.com/services/rest/"
KOREANET = "42438955@N05"           # KOREA.NET - Official page of the Republic of Korea
LICENSES = "4,5,9,10"               # CC BY 2.0, CC BY-SA 2.0, CC0, Public Domain Mark
LIC_NAME = {"4": "CC BY 2.0", "5": "CC BY-SA 2.0", "9": "CC0", "10": "Public domain"}
DIR = "event_photos"
DAYS = int(os.getenv("EVENT_PHOTO_DAYS", "3"))
_USED: set[str] = set()   # 한 게시물 안에서 같은 사진 중복 방지


def _search(text: str) -> list[dict]:
    key = os.getenv("FLICKR_API_KEY")
    if not key or not text:
        return []
    r = requests.get(API, timeout=30, params={
        "method": "flickr.photos.search", "api_key": key, "user_id": KOREANET,
        "text": text, "license": LICENSES, "sort": "relevance",
        "min_upload_date": int(time.time()) - DAYS * 86400,
        "content_types": 0, "media": "photos", "per_page": 5,
        "extras": "url_l,url_c,license,date_taken", "format": "json", "nojsoncallback": 1})
    data = r.json()
    if data.get("stat") != "ok":
        print(f"[event] Flickr 오류: {data.get('message')}")
        return []
    return [p for p in data["photos"]["photo"] if p.get("url_l") or p.get("url_c")]


def get_event_photo(queries: list[str], tag: str) -> tuple[str, str] | None:
    """검색어 후보를 순서대로 시도해 첫 결과 사진을 받아 (경로, 출처) 반환."""
    for q in [q for q in queries if q]:
        try:
            hits = _search(q)
        except Exception as e:
            print(f"[event] 검색 실패({q}): {e}")
            continue
        hits = [h for h in hits if h["id"] not in _USED]
        if not hits:
            continue
        p = hits[0]
        _USED.add(p["id"])
        url = p.get("url_l") or p["url_c"]
        os.makedirs(DIR, exist_ok=True)
        path = os.path.join(DIR, f"{p['id']}.jpg")
        if not os.path.exists(path):
            img = requests.get(url, timeout=60)
            if img.status_code != 200:
                continue
            open(path, "wb").write(img.content)
        lic = LIC_NAME.get(str(p.get("license")), "CC BY-SA 2.0")
        print(f"[event] '{q}' → {p.get('title', '')[:40]}")
        return path, f"사진: Korea.net(대한민국 정부) / {lic} / Flickr"
    return None
