"""GitHub Actions: 게시 시간이 된 대기열(queue/<채널>/<id>/) 게시물을 인스타에 올린다. (Claude 호출 없음 → 0원)

사용법: python publish_queue.py --channel right
- meta.json 의 publish_at 이 지났고 published.json 이 없는 것 중 가장 오래된 1개만 게시(스팸 방지)
- meta.reel 이 true 면(아침 게시물) 같은 카드로 릴스를 만들어 이어서 게시
- 게시 후 published.json 기록, 5일 지난 게시 완료 폴더는 삭제(저장소 용량 관리)

[중복 게시 방지 — 2026-11-15 사고 후 추가]
- 게시를 '시도하기 전에' attempt.json 을 만든다. attempt.json 이 있는 게시물은 다시 시도하지 않는다
  (게시 도중 오류가 나도 인스타에는 이미 올라갔을 수 있으므로). 다시 올리려면 attempt.json 을 지워야 함
- 오류가 나면 인스타 최근 게시물에서 같은 캡션을 찾아, 실제로 올라갔으면 published.json 으로 기록
- 게시 시간이 3시간 넘게 지난 게시물은 올리지 않고 건너뜀(오래된 뉴스 방지)
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

import traceback

from buzz.publish import _get, publish_carousel

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


def already_on_instagram(caption: str):
    """오류 뒤 확인: 최근 게시물 중 캡션 앞부분이 같은 게 있으면 그 media_id."""
    try:
        user = os.getenv("IG_USER_ID") or "me"
        items = _get(f"{user}/media", fields="id,caption,timestamp", limit=15).get("data", [])
        head = caption.strip()[:80]
        return next((m["id"] for m in items if (m.get("caption") or "").strip()[:80] == head), None)
    except Exception as e:
        print(f"[{cid}] 최근 게시물 확인 실패: {e}")
        return None


changed = False
pending = []
for d in sorted(glob.glob(f"queue/{cid}/*/")):
    meta_p = os.path.join(d, "meta.json")
    if not os.path.exists(meta_p) or os.path.exists(os.path.join(d, "published.json")) \
            or os.path.exists(os.path.join(d, "attempt.json")):
        continue
    meta = json.load(open(meta_p, encoding="utf-8"))
    at = datetime.fromisoformat(meta["publish_at"])
    if at <= now + timedelta(minutes=15):
        if now - at > timedelta(hours=3):
            json.dump({"skipped": "게시 시간 3시간 초과", "at": now.isoformat()},
                      open(os.path.join(d, "attempt.json"), "w", encoding="utf-8"), ensure_ascii=False)
            print(f"[{cid}] {meta['id']} 게시 시간이 지나 건너뜀")
            changed = True
            continue
        pending.append((d, meta))

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
        att = os.path.join(d, "attempt.json")
        json.dump({"started_at": now.isoformat()}, open(att, "w", encoding="utf-8"))
        changed = True
        dup = already_on_instagram(caption)     # 기록이 저장 안 됐던 경우 대비: 이미 올라가 있으면 다시 안 올림
        if dup:
            print(f"[{cid}] 이미 인스타에 같은 게시물이 있음({dup}) → 다시 올리지 않고 완료로 기록")
            json.dump({"media_id": dup, "published_at": now.isoformat(), "note": "이미 게시돼 있었음"},
                      open(os.path.join(d, "published.json"), "w", encoding="utf-8"))
            meta["reel"] = False
            reel = None
            pending = pending[:1]
        try:
            if dup:
                raise StopIteration
            record = {"media_id": publish_carousel(urls, caption), "published_at": now.isoformat()}
        except StopIteration:
            record = None
        except Exception as e:
            err = "".join(traceback.format_exception(e))[-1500:]
            print(f"[{cid}] 게시 중 오류:\n{err}")
            mid = already_on_instagram(caption)
            json.dump({"started_at": now.isoformat(), "error": err, "found_on_instagram": mid},
                      open(att, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            if not mid:
                open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a").write("changed=true\n")
                sys.exit(1)       # 실패 알림용(기록은 남김 → 다음 실행 때 다시 시도하지 않음)
            print(f"[{cid}] 오류가 났지만 인스타에는 올라가 있음({mid}) → 게시 완료로 기록")
            record = {"media_id": mid, "published_at": now.isoformat(), "note": "오류 후 확인"}
            reel = None
        if record and reel:
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
        if record:
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
