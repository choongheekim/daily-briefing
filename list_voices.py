"""타입캐스트 남성/여성 목소리 목록 + 미리듣기 링크 출력.

사용법(PC): python list_voices.py  → API 키 붙여넣기
마음에 드는 voice_id 를 GitHub Secret TYPECAST_VOICE_RIGHT / TYPECAST_VOICE_LEFT 에 넣으세요.
(넣지 않으면 봇이 중년 남성·뉴스 계열 목소리를 자동으로 고릅니다)
"""
import os

import requests

key = (os.getenv("TYPECAST_API_KEY") or input("타입캐스트 API 키를 붙여넣고 Enter: ")).strip()
r = requests.get("https://api.typecast.ai/v3/voices", headers={"X-API-KEY": key},
                 params={"model": "ssfm-v31", "voice_type": "original"}, timeout=30)
r.raise_for_status()
for v in r.json():
    emos = {e for m in v.get("models", []) for e in m.get("emotions", [])}
    if "angry" not in emos and "toneup" not in emos:
        continue
    name = (v.get("voice_name") or {}).get("kor", "")
    print(f"{v['voice_id']:<28} {name:<10} {v.get('gender') or '':<7} {v.get('age') or '':<12} "
          f"{','.join(v.get('use_cases') or [])[:30]:<30} {v.get('preview_url') or ''}")
