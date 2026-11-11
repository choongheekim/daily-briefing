"""분위기·장소 배경 사진: Pexels API (무료 키, 원본 고화질).

정치인 사진이 아니라 국회·법원·경제 같은 '분위기 배경'으로만 쓴다.
사람이 주인공인 사진(설명에 man/woman/people 등)은 건너뛴다(초상권·광고처럼 보이는 것 방지).
Pexels 규칙: 사진작가 이름 표기 + Pexels 링크(캡션에 자동으로 넣음).

필요: PEXELS_API_KEY (무료, https://www.pexels.com/api/)
"""
import os
import re

import requests

DIR = "pexels_cache"
_USED: set[int] = set()
PEOPLE = re.compile(r"\b(man|men|woman|women|person|people|girl|boy|child|portrait|face|couple|"
                    r"businessman|crowd|selfie|model)\b", re.I)
USED_ANY = {"flag": False}


def get_scene(query: str | None) -> tuple[str, str] | None:
    key = os.getenv("PEXELS_API_KEY")
    if not key or not query:
        return None
    try:
        r = requests.get("https://api.pexels.com/v1/search", headers={"Authorization": key}, timeout=30,
                         params={"query": query, "orientation": "portrait", "size": "large",
                                 "per_page": 15, "locale": "en-US"})
        r.raise_for_status()
        photos = r.json().get("photos", [])
    except Exception as e:
        print(f"[pexels] 검색 실패({query}): {e}")
        return None
    for p in photos:
        if p["id"] in _USED or p.get("width", 0) < 1600 or PEOPLE.search(p.get("alt") or ""):
            continue
        os.makedirs(DIR, exist_ok=True)
        path = os.path.join(DIR, f"{p['id']}.jpg")
        if not os.path.exists(path):
            img = requests.get(p["src"]["original"] + "?auto=compress&cs=tinysrgb&w=2000", timeout=90)
            if img.status_code != 200:
                continue
            open(path, "wb").write(img.content)
        _USED.add(p["id"])
        USED_ANY["flag"] = True
        print(f"[pexels] '{query}' → {p.get('alt', '')[:40]} / {p['photographer']}")
        return path, f"사진: {p['photographer'][:24]} / Pexels"
    return None
