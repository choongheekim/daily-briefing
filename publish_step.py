"""채널의 오늘 카드뉴스를 인스타에 게시하고 history_<채널>.json 갱신.

사용법: python publish_step.py --channel right
(IG_ACCESS_TOKEN 환경변수에 해당 채널 계정의 토큰)
"""
import argparse
import glob
import json
import os
from datetime import datetime

from bot.news import KST
import subprocess

from bot.publish import publish_carousel, publish_reel, wait_url

ap = argparse.ArgumentParser()
ap.add_argument("--channel", required=True, choices=["right", "left"])
cid = ap.parse_args().channel

today = datetime.now(KST).strftime("%Y-%m-%d")
out_dir = f"posts/{cid}/{today}"
repo = os.environ["GITHUB_REPOSITORY"]
branch = os.getenv("GITHUB_REF_NAME", "main")

images = sorted(glob.glob(f"{out_dir}/*.jpg"))
urls = [f"https://raw.githubusercontent.com/{repo}/{branch}/{p}" for p in images]
caption = open(f"{out_dir}/caption.txt", encoding="utf-8").read()
content = json.load(open(f"{out_dir}/content.json", encoding="utf-8"))

media_id = publish_carousel(urls, caption)

# ── 릴스 (있으면)
reel_id = None
reel = f"{out_dir}/reel.mp4"
if os.getenv("REELS", "1") == "1" and os.path.exists(reel):
    rcap = open(f"{out_dir}/reel_caption.txt", encoding="utf-8").read()
    try:
        reel_id = publish_reel(reel, rcap)                      # 직접 업로드
    except Exception as e:
        print(f"[reels] 직접 업로드 실패 → 공개 주소 방식으로 재시도: {e}")
        try:
            subprocess.run(["git", "add", "-f", reel], check=True)
            subprocess.run(["git", "commit", "-qm", f"{cid} reel {today}"], check=True)
            subprocess.run(["git", "pull", "-q", "--rebase", "-X", "theirs"], check=True)
            subprocess.run(["git", "push", "-q"], check=True)
            url = f"https://raw.githubusercontent.com/{repo}/{branch}/{reel}"
            wait_url(url)
            reel_id = publish_reel(reel, rcap, public_url=url)
        except Exception as e2:
            print(f"[reels] 릴스 게시 실패(카드 게시는 완료): {e2}")

hp = f"history_{cid}.json"
history = json.load(open(hp, encoding="utf-8")) if os.path.exists(hp) else []
history.append({"date": today, "media_id": media_id, "reel_id": reel_id,
                "headlines": [s["headline"] for s in content["stories"]]})
json.dump(history[-30:], open(hp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
