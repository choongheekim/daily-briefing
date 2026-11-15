"""중복 게시물 정리(수동 실행용). 같은 캡션으로 여러 번 올라간 게시물 중 '가장 먼저 올라간 1개'만 남긴다.

사용법(GitHub Actions의 cleanup-duplicates 워크플로에서 실행):
  python cleanup_dupes.py --channel right            목록만 보기(아무것도 안 지움)
  python cleanup_dupes.py --channel right --delete   목록의 중복 게시물 삭제(되돌릴 수 없음)
"""
import argparse
import os
from collections import defaultdict

import requests

from buzz.publish import API, _get, _token

ap = argparse.ArgumentParser()
ap.add_argument("--channel", required=True)
ap.add_argument("--delete", action="store_true")
a = ap.parse_args()
user = os.getenv("IG_USER_ID")

items, url, params = [], f"{user}/media", {"fields": "id,caption,timestamp,media_product_type,permalink", "limit": 50}
data = _get(url, **params)
items += data.get("data", [])
nxt = data.get("paging", {}).get("next")
if nxt and len(items) < 100:
    items += requests.get(nxt, timeout=60).json().get("data", [])

groups = defaultdict(list)
for m in items:
    key = (m.get("media_product_type"), (m.get("caption") or "").strip()[:80])
    if key[1]:
        groups[key].append(m)

extra = []
for (kind, head), ms in groups.items():
    if len(ms) < 2:
        continue
    ms.sort(key=lambda m: m["timestamp"])
    keep, dupes = ms[0], ms[1:]
    print(f"\n[{a.channel}] {kind} 중복 {len(ms)}개: {head[:40]}…")
    print(f"  남김: {keep['timestamp']} {keep['permalink']}")
    for m in dupes:
        print(f"  삭제 대상: {m['timestamp']} {m['permalink']}")
    extra += dupes

print(f"\n[{a.channel}] 최근 게시물 {len(items)}개 중 중복 {len(extra)}개")
if a.delete:
    ok = 0
    for m in extra:
        r = requests.delete(f"{API}/{m['id']}", params={"access_token": _token()}, timeout=60)
        if r.status_code == 200:
            ok += 1
        else:
            print(f"  삭제 실패 {m['permalink']}: {r.status_code} {r.text[:200]}")
    print(f"[{a.channel}] 삭제 완료 {ok}/{len(extra)}")
