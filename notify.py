"""텔레그램 알림(개인 비서봇). 토큰이 없으면 조용히 건너뜀.

사용법: python notify.py "메시지"
환경변수 TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (GitHub Secret 또는 PC 설정 파일)
"""
import os
import sys

import requests


def send(text: str) -> bool:
    tok, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not tok or not chat:
        print(f"[알림 생략 — 텔레그램 설정 없음] {text}")
        return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=20,
                          data={"chat_id": chat, "text": text})
        return r.ok
    except requests.RequestException as e:
        print(f"[알림 실패] {e}")
        return False


if __name__ == "__main__":
    send(" ".join(sys.argv[1:]) or "알림 테스트")
