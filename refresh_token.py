"""인스타 장기 토큰 갱신 → 새 토큰을 표준출력으로 (워크플로가 secret 갱신)."""
from bot.publish import refresh_token

print(refresh_token())
