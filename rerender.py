"""이미 만든 카드뉴스를 인물 사진을 넣어 다시 그린다.

사용법 (이 폴더에서):
  pip install -r requirements.txt
  python rerender.py --channel left  --date 2026-11-10
  python rerender.py --channel right --date 2026-11-10

posts/<채널>/<날짜>/content.json 을 읽어 같은 폴더에 01~07.jpg 를 다시 만든다.
인물 사진은 위키미디어 공용에서 자유 라이선스 사진만 받고, 카드에 저작자·라이선스를 표기한다.
"""
import argparse
import json
import os

os.environ.setdefault("AUTO_PHOTO", "1")

from bot.render import render_all, sanitize, set_theme  # noqa: E402
from main import load_channel, make_caption  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--channel", required=True, choices=["right", "left"])
ap.add_argument("--date", required=True, help="예: 2026-11-10")
a = ap.parse_args()

out = os.path.join("posts", a.channel, a.date)
content = json.load(open(os.path.join(out, "content.json"), encoding="utf-8"))
set_theme(load_channel(a.channel))
content = sanitize(content)
paths = render_all(content, out)
with open(os.path.join(out, "caption.txt"), "w", encoding="utf-8") as f:
    f.write(make_caption(content))
print(f"완료: {out} 에 {len(paths)}장")
