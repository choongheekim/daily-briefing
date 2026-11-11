"""Pexels 분위기 사진(실물 사진이 없을 때만). PEXELS_API_KEY 없으면 건너뜀."""
import hashlib
import os

import requests

UA = {"User-Agent": "hottopic-zip/1.0 (https://github.com/choongheekim/hottopic-zip)"}


def search(query: str, n: int = 3) -> list[dict]:
    key = os.getenv("PEXELS_API_KEY", "").strip()
    if not key:
        return []
    try:
        r = requests.get("https://api.pexels.com/v1/search", headers={"Authorization": key, **UA}, timeout=30,
                         params={"query": query, "per_page": 10, "orientation": "portrait"})
        photos = r.json().get("photos", []) if r.status_code == 200 else []
    except (requests.RequestException, ValueError):
        return []
    out = []
    for p in photos:
        if p["width"] < 1000:
            continue
        out.append({"title": p.get("alt") or query, "w": p["width"], "h": p["height"],
                    "thumb": p["src"]["original"] + "?auto=compress&w=1920", "page": p["url"],
                    "license": "Pexels License", "artist": p["photographer"], "share_alike": False,
                    "credit": f"Photo: {p['photographer']} / Pexels", "stock": True})
        if len(out) >= n:
            break
    return out


def download(c: dict, cache="image_cache") -> str | None:
    os.makedirs(cache, exist_ok=True)
    path = os.path.join(cache, "px_" + hashlib.md5(c["thumb"].encode()).hexdigest()[:12] + ".jpg")
    if os.path.exists(path):
        return path
    try:
        r = requests.get(c["thumb"], headers=UA, timeout=60)
        if r.status_code == 200:
            open(path, "wb").write(r.content)
            return path
    except requests.RequestException:
        pass
    return None
