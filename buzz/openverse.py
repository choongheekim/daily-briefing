"""오픈버스(Openverse)로 플리커 CC 사진 찾기 — 특히 정부 공식 계정 '코리아넷(KOREA.NET)' 현장 사진.

- 키 필요 없음(익명 사용, 횟수 제한 있음)
- 허용 라이선스: CC0, PDM, CC BY, CC BY-SA (NC·ND 제외)
- 코리아넷 사진은 대통령·총리 일정, 정부 행사 사진이 많음 → 뉴스와 바로 맞는 '현장 사진'
"""
import hashlib
import os
import time

import requests

API = "https://api.openverse.org/v1/images/"
UA = {"User-Agent": "daily-briefing/1.0 (https://github.com/choongheekim/daily-briefing)"}
KOREANET = "KOREA.NET - Official page of the Republic of Korea"
CACHE = "image_cache"
LIC = {"cc0": "CC0", "pdm": "Public domain", "by": "CC BY", "by-sa": "CC BY-SA"}


def search(query: str, limit: int = 4, koreanet_only: bool = True) -> list[dict]:
    params = {"q": query, "source": "flickr", "license": "cc0,pdm,by,by-sa", "page_size": 20, "mature": "false"}
    try:
        r = requests.get(API, headers=UA, params=params, timeout=30)
        items = r.json().get("results", []) if r.status_code == 200 else []
    except (requests.RequestException, ValueError):
        return []
    out = []
    for it in items:
        if koreanet_only and it.get("creator") != KOREANET:
            continue
        w, h = it.get("width") or 0, it.get("height") or 0
        if max(w, h) < 900:
            continue
        lic = f"{LIC.get(it['license'], it['license'].upper())} {it.get('license_version') or ''}".strip()
        who = "KOREA.NET" if it.get("creator") == KOREANET else (it.get("creator") or "Flickr")
        out.append({"title": it.get("title") or "", "w": w, "h": h, "thumb": it["url"],
                    "page": it.get("foreign_landing_url"), "license": lic, "artist": who,
                    "desc": (it.get("title") or "")[:160], "share_alike": "SA" in lic,
                    "credit": f"Photo: {who} / {lic}", "koreanet": it.get("creator") == KOREANET})
        if len(out) >= limit:
            break
    return out


def download(c: dict) -> str | None:
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, "ov_" + hashlib.md5(c["thumb"].encode()).hexdigest()[:12] + ".jpg")
    if os.path.exists(path):
        return path
    for i in range(3):
        try:
            r = requests.get(c["thumb"], headers=UA, timeout=60)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
                from io import BytesIO
                from PIL import Image
                Image.open(BytesIO(r.content)).convert("RGB").save(path, quality=92)
                return path
        except requests.RequestException:
            pass
        time.sleep(5 * (i + 1))
    return None
