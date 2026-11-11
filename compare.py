"""개선 전후 카드 비교 이미지 만들기.

사용법: python compare.py --channel right --date 2026-11-11
- 그날 이미 게시된 카드(posts/<채널>/<날짜>/01~07.jpg)를 '전'으로,
- 같은 문구(content.json)를 지금 코드로 다시 그린 카드를 '후'로 나란히 붙인다.
결과: compare/<채널>_<날짜>_NN.jpg (게시 안 함, Claude 호출 없음)
"""
import argparse
import json
import os
import shutil
import tempfile

from PIL import Image, ImageDraw

from bot.render import font, render_all, set_theme

ap = argparse.ArgumentParser()
ap.add_argument("--channel", required=True, choices=["right", "left"])
ap.add_argument("--date", required=True)
a = ap.parse_args()

ch = json.load(open(f"channels/{a.channel}.json", encoding="utf-8"))
set_theme(ch)
src = f"posts/{a.channel}/{a.date}"
content = json.load(open(f"{src}/content.json", encoding="utf-8"))
tmp = tempfile.mkdtemp()
new = render_all(content, tmp)
os.makedirs("compare", exist_ok=True)
for i, n in enumerate(new, 1):
    old_p = f"{src}/{i:02d}.jpg"
    if not os.path.exists(old_p):
        continue
    o, nw = Image.open(old_p).convert("RGB"), Image.open(n).convert("RGB")
    canvas = Image.new("RGB", (o.width * 2 + 40, o.height + 110), (30, 30, 34))
    canvas.paste(o, (0, 110))
    canvas.paste(nw, (o.width + 40, 110))
    d = ImageDraw.Draw(canvas)
    d.text((30, 25), "전 (지금)", font=font(56, "black"), fill=(220, 220, 220))
    d.text((o.width + 70, 25), "후 (개선)", font=font(56, "black"), fill=(255, 214, 0))
    canvas.resize((canvas.width // 2, canvas.height // 2), Image.LANCZOS).save(
        f"compare/{a.channel}_{a.date}_{i:02d}.jpg", quality=88)
print("photo_credits:", content.get("photo_credits"))
shutil.rmtree(tmp, ignore_errors=True)
