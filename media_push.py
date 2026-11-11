"""오늘 카드 이미지·릴스를 'media-<채널>' 브랜치에 올려 인스타가 가져갈 공개 주소를 만든다.

main 브랜치에는 이미지·영상을 더 이상 쌓지 않는다(저장소가 매일 35MB씩 커지던 문제 해결).
media 브랜치는 매번 '오늘 것만' 남기고 통째로 덮어쓰기 때문에 용량이 늘지 않는다.

사용법: python media_push.py --channel right   (GitHub Actions 안에서 실행)
"""
import argparse
import glob
import os
import shutil
import subprocess
import tempfile
from datetime import datetime

from bot.news import KST

ap = argparse.ArgumentParser()
ap.add_argument("--channel", required=True, choices=["right", "left"])
cid = ap.parse_args().channel
today = os.getenv("POST_DATE") or datetime.now(KST).strftime("%Y-%m-%d")
src = f"posts/{cid}/{today}"
files = sorted(glob.glob(f"{src}/*.jpg")) + sorted(glob.glob(f"{src}/reel.mp4"))
if not files:
    raise SystemExit(f"올릴 파일 없음: {src}")

repo = os.environ.get("GITHUB_REPOSITORY", "")
remote = os.getenv("MEDIA_REMOTE") or f"https://x-access-token:{os.environ['GH_TOKEN']}@github.com/{repo}.git"
branch = f"media-{cid}"
tmp = tempfile.mkdtemp()
dst = os.path.join(tmp, cid, today)
os.makedirs(dst)
for f in files:
    shutil.copy(f, dst)


def git(*a):
    subprocess.run(["git", *a], cwd=tmp, check=True)


git("init", "-q", "-b", branch)
git("config", "user.name", "news-bot")
git("config", "user.email", "news-bot@users.noreply.github.com")
git("add", ".")
git("commit", "-qm", f"{cid} media {today}")
git("push", "-q", "--force", remote, f"{branch}:{branch}")
print(f"[media] {len(files)}개 → {branch} 브랜치")
shutil.rmtree(tmp, ignore_errors=True)
