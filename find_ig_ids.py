"""토큰으로 연결된 인스타 계정 ID 찾기.

사용법: 계정ID_찾기.bat 더블클릭 → 토큰 붙여넣기 (또는 python find_ig_ids.py)
출력된 ID를 GitHub Secret IG_USER_ID_RIGHT / IG_USER_ID_LEFT 에 넣는다.
"""
import os

import requests

V = os.getenv("IG_API_VERSION", "v25.0")
TOKEN = (os.getenv("IG_ACCESS_TOKEN") or input("토큰을 붙여넣고 Enter: ")).strip()


def get(host, path, **p):
    p["access_token"] = TOKEN
    r = requests.get(f"https://{host}/{V}/{path}", params=p, timeout=30)
    return r.status_code, r.json()


found = {}
st, me = get("graph.facebook.com", "me", fields="id,name")
print("토큰 주인:", me)

# 0) 통합 로그인(시스템 사용자 토큰): 배정된 인스타 계정
st, r = get("graph.facebook.com", "me/assigned_instagram_accounts", fields="id,username")
for a in r.get("data", []):
    found[a.get("username")] = a["id"]
if not r.get("data"):
    print("assigned_instagram_accounts 응답:", r)

# 1) 시스템 사용자에 배정된 비즈니스 → 소유 인스타 계정
st, biz = get("graph.facebook.com", "me/businesses", fields="id,name")
for b in biz.get("data", []):
    for edge in ("owned_instagram_accounts", "instagram_business_accounts"):
        st, r = get("graph.facebook.com", f"{b['id']}/{edge}", fields="id,username")
        for a in r.get("data", []):
            found[a.get("username")] = a["id"]

# 2) 페이지에 연결된 인스타 계정
st, pages = get("graph.facebook.com", "me/accounts", fields="name,instagram_business_account{id,username}")
for p in pages.get("data", []):
    a = p.get("instagram_business_account")
    if a:
        found[a.get("username")] = a["id"]

if found:
    print("\n인스타 계정 ID:")
    for u, i in found.items():
        print(f"  @{u}: {i}")
else:
    print("\n자동으로 찾지 못했습니다. 비즈니스 설정 > 계정 > Instagram 계정에서 계정을 누르면 ID가 보입니다.")
    print("응답:", biz, pages)
