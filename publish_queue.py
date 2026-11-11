"""GitHub Actions: 게시 시간이 된 대기열(queue/<채널>/<id>/) 게시물을 인스타에 올린다. (Claude 호출 없음 → 0원)

사용법: python publish_queue.py --channel right
- meta.json 의 publish_at 이 지났고 published.json 이 없는 것 중 가장 오래된 1개만 게시(스팸 방지)
- meta.reel 이 true 면(아침 게시물) 같은 카드로 릴스를 만들어 이어서 게시
- 게시 후 published.json 기록, 5일 지난 게시 완료 폴더는 삭제(저장소 용량 관리)
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

from buzz.publish import publish_carousel

KST = timezone(timedelta(hours=9))
ap = argparse.ArgumentParser()
ap.add_argument("--channel", required=True, choices=["right", "left"])
cid = ap.parse_args().channel
now = datetime.now(KST)
repo = os.environ["GITHUB_REPOSITORY"]
branch = os.getenv("GITHUB_REF_NAME", "main")
dry = os.getenv("DRY_RUN", "false") == "true"


def reel_public_url(path: str, pid: str) -> str:
    """직접 업로드가 막힐 때: 영상을 media-<채널> 브랜치(그날 것만 덮어씀)에 올려 공개 주소를 만든다."""
    tmp = tempfile.mkdtemp()
    shutil.copy(path, os.path.join(tmp, f"{pid}.mp4"))
    run = lambda *a: subprocess.run(["git", *a], cwd=tmp, check=True)
    run("init", "-q", "-b", f"media-{cid}")
    run("config", "user.name", "news-bot")
    run("config", "user.email", "news-bot@users.noreply.github.com")
    run("add", ".")
    run("commit", "-qm", f"reel {pid}")
    run("push", "-q", "--force", f"https://x-access-token:{os.environ['GH_TOKEN']}@github.com/{repo}.git",
        f"media-{cid}:media-{cid}")
    return f"https://raw.githubusercontent.com/{repo}/media-{cid}/{pid}.mp4"


pending = []
for d in sorted(glob.glob(f"queue/{cid}/*/")):
    meta_p = os.path.join(d, "meta.json")
    if not os.path.exists(meta_p) or os.path.exists(os.path.join(d, "published.json")):
        continue
    meta = json.load(open(meta_p, encoding="utf-8"))
    if datetime.fromisoformat(meta["publish_at"]) <= now + timedelta(minutes=15):
        pending.append((d, meta))

changed = False
if not pending:
    print(f"[{cid}] 게시할 대기열 없음")
else:
    d, meta = pending[0]
    images = sorted(glob.glob(os.path.join(d, "[0-9][0-9].jpg")))
    urls = [f"https://raw.githubusercontent.com/{repo}/{branch}/{p.replace(os.sep, '/')}" for p in images]
    caption = open(os.path.join(d, "caption.txt"), encoding="utf-8").read()
    print(f"[{cid}] 게시: {meta['id']} {meta['topic']} ({len(urls)}장, 릴스 {'O' if meta.get('reel') else 'X'})")
    reel = None
    if meta.get("reel"):
        try:
            from buzz.reel import build
            reel = build(images, meta.get("reel_script", {}), os.path.join(tempfile.mkdtemp(), "reel.mp4"),
                         tempfile.mkdtemp())
            os.makedirs("preview", exist_ok=True)
            shutil.copy(reel, f"preview/{cid}_{meta['id']}_reel.mp4")
        except Exception as e:
            print(f"[{cid}] 릴스 만들기 실패(카드는 게시): {e}")
    if dry:
        print("DRY_RUN — 실제 게시 안 함", urls[:2])
    else:
        record = {"media_id": publish_carousel(urls, caption), "published_at": now.isoformat()}
        if reel:
            from bot.publish import publish_reel
            rcap = caption.split("\n\n출처:")[0] + f"\n\n👉 카드 {len(images)}장 전체는 피드 게시물에서"
            try:
                try:
                    record["reel_id"] = publish_reel(reel, rcap[:2150])
                except Exception as e:
                    print(f"[{cid}] 릴스 직접 업로드 실패 → 공개 주소로 재시도: {e}")
                    record["reel_id"] = publish_reel(reel, rcap[:2150], reel_public_url(reel, meta["id"]))
            except Exception as e:
                print(f"[{cid}] 릴스 게시 실패(카드는 게시됨): {e}")
        json.dump(record, open(os.path.join(d, "published.json"), "w", encoding="utf-8"))
        changed = True
    if len(pending) > 1:
        print(f"[{cid}] 남은 대기 {len(pending) - 1}개 → 다음 실행 때 게시")

for d in glob.glob(f"queue/{cid}/*/"):
    pj = os.path.join(d, "published.json")
    if os.path.exists(pj):
        t = datetime.fromisoformat(json.load(open(pj))["published_at"])
        if now - t > timedelta(days=5):
            shutil.rmtree(d)
            changed = True
open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a").write(f"changed={'true' if changed else 'false'}\n")
sys.exit(0)
