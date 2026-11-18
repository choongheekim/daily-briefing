"""GitHub Actions: 게시 시간이 된 대기열(queue/<채널>/<id>/) 게시물을 인스타에 올린다. (Claude 호출 없음 → 0원)

사용법: python publish_queue.py --channel right
- meta.json 의 publish_at 이 지났고 published.json 이 없는 것 중 가장 오래된 1개만 게시(스팸 방지)
- meta.reel 이 true 면 같은 내용으로 쇼츠(릴스)를 만들어 이어서 게시
- 게시 후 published.json 기록, 5일 지난 게시 완료 폴더는 삭제(저장소 용량 관리)

[중복 게시 방지 — 2026-11-15 사고 후 추가]
- 게시를 '시도하기 전에' attempt.json 을 만든다. attempt.json 이 있는 게시물은 다시 시도하지 않는다
- 오류가 나면 인스타 최근 게시물에서 같은 캡션을 찾아, 실제로 올라갔으면 published.json 으로 기록
- 게시 시간이 3시간 넘게 지난 게시물은 올리지 않고 건너뜀(오래된 뉴스 방지)

[2026-11-16 원인 확인] 인스타가 media_publish 에 403(코드 4 / 2207051 '행동이 차단되었습니다')을
돌려줘도 실제로는 게시가 되는 경우가 있음 → 이때는 성공으로 보고 릴스도 이어서 올린다.
게시 단계(media_publish)에서 난 오류는 다른 방법으로 다시 올리지 않는다(중복 방지).
- 피드는 올라갔는데 릴스가 빠진 게시물(3시간 이내)은 다음 실행 때 릴스만 한 번 더 시도한다.
"""
import nowindow  # noqa: F401  윈도우 검은 창 안 뜨게 (가장 먼저)
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from datetime import datetime, timedelta, timezone

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


def already_on_instagram(caption: str, kind: str = "feed"):
    """최근 게시물 중 캡션 앞부분이 같은 게 있으면 그 media_id. kind=feed(카드) / reel(영상)"""
    try:
        user = os.getenv("IG_USER_ID") or "me"
        items = _get(f"{user}/media", fields="id,caption,media_type,timestamp", limit=20).get("data", [])
        head = caption.strip()[:80]
        for m in items:
            is_video = m.get("media_type") == "VIDEO"
            if (kind == "reel") != is_video:
                continue
            if (m.get("caption") or "").strip()[:80] == head:
                return m["id"]
        return None
    except Exception as e:
        print(f"[{cid}] 최근 게시물 확인 실패: {e}")
        return None


def build_reel(d, images, meta):
    try:
        from buzz.reel import build
        reel = build(images, meta.get("reel_script", {}), os.path.join(tempfile.mkdtemp(), "reel.mp4"),
                     tempfile.mkdtemp())
        os.makedirs("preview", exist_ok=True)
        shutil.copy(reel, f"preview/{cid}_{meta['id']}_reel.mp4")
        save_short(reel, d, meta)
        return reel
    except Exception as e:
        print(f"[{cid}] 릴스 만들기 실패: {e}")
        return None


def save_short(reel, d, meta):
    """유튜브 쇼츠 수동 업로드용: 영상과 제목·설명을 GitHub '릴리스(shorts)'에 올려 둔다(로그인 없이 받기 가능)."""
    if dry:
        return
    try:
        name = f"{cid}_{meta['id']}"
        cap = open(os.path.join(d, "caption.txt"), encoding="utf-8").read()
        body = cap.split("\n\n출처:")[0].strip()
        tags = " ".join(t for t in cap.split() if t.startswith("#"))[:300]
        title = meta.get("topic", "")[:88] + " #shorts"
        txt = os.path.join(tempfile.mkdtemp(), name + ".txt")
        open(txt, "w", encoding="utf-8").write(f"[제목]\n{title}\n\n[설명]\n{body}\n\n{tags}\n")
        mp4 = os.path.join(os.path.dirname(txt), name + ".mp4")
        shutil.copy(reel, mp4)
        env = dict(os.environ)
        if subprocess.run(["gh", "release", "view", "shorts", "-R", repo], env=env, capture_output=True).returncode:
            subprocess.run(["gh", "release", "create", "shorts", "-R", repo, "--title", "유튜브 쇼츠 보관함",
                            "--notes", "자동으로 만든 쇼츠 영상(수동 업로드용)"], env=env, check=True)
        subprocess.run(["gh", "release", "upload", "shorts", mp4, txt, "-R", repo, "--clobber"], env=env, check=True)
        print(f"[{cid}] 쇼츠 보관함에 올림: {name}.mp4")
    except Exception as e:
        print(f"[{cid}] 쇼츠 보관함 올리기 실패: {e}")


def tg_short(reel, d, meta, rid):
    """쇼츠 영상 + 유튜브용 제목·설명을 텔레그램으로 보냄(유튜브는 사람이 직접 올림).
    GitHub Secret TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 가 있어야 동작."""
    tok, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not tok or not chat or dry or not reel:
        return
    import html
    import requests
    try:
        name = "보수의 아침" if cid == "right" else "진보의 아침"
        cap = open(os.path.join(d, "caption.txt"), encoding="utf-8").read()
        body = cap.split("\n\n#")[0].strip()
        tags = [t for t in cap.split() if t.startswith("#")][:10]
        desc = (body + "\n\n" + " ".join(tags + ["#shorts"])).replace("한마디는 이 계정의 의견", "한마디는 이 채널의 의견")
        title = (meta.get("topic", "")[:88] + " #shorts")
        api = f"https://api.telegram.org/bot{tok}"
        with open(reel, "rb") as f:
            requests.post(f"{api}/sendVideo", timeout=180, files={"video": (f"{cid}_{meta['id']}.mp4", f, "video/mp4")},
                          data={"chat_id": chat, "supports_streaming": "true", "width": 1080, "height": 1920,
                                "caption": f"🎬 [{name}] 쇼츠 — 인스타 릴스 {'게시됨' if rid else '게시 안 됨(확인 필요)'}\n"
                                           f"아래 제목·설명을 눌러 복사해서 유튜브에 올리세요."})
        for label, text in (("📌 제목", title), ("📝 설명", desc[:3500])):
            requests.post(f"{api}/sendMessage", timeout=60, data={
                "chat_id": chat, "parse_mode": "HTML",
                "text": f"{label}\n<code>{html.escape(text)}</code>"})
        print(f"[{cid}] 텔레그램으로 쇼츠 보냄")
    except Exception as e:
        print(f"[{cid}] 텔레그램 보내기 실패: {e}")


def post_reel(reel, caption, n_cards, pid):
    """릴스 게시. 성공하거나 이미 올라가 있으면 media_id, 아니면 None"""
    from bot.publish import publish_reel
    rcap = (caption.split("\n\n출처:")[0] + f"\n\n👉 카드 {n_cards}장 전체는 피드 게시물에서")[:2150]
    try:
        return publish_reel(reel, rcap)
    except Exception as e:
        print(f"[{cid}] 릴스 게시 오류: {str(e)[:400]}")
        found = already_on_instagram(rcap, "reel")
        if found:
            print(f"[{cid}] 오류가 났지만 릴스는 올라가 있음({found})")
            return found
        if "media_publish" in str(e):      # 게시 단계 오류 → 다른 방법으로 다시 올리지 않음(중복 방지)
            return None
    try:
        return publish_reel(reel, rcap, reel_public_url(reel, pid))
    except Exception as e:
        print(f"[{cid}] 릴스 공개 주소 방식도 실패: {str(e)[:400]}")
        return already_on_instagram(rcap, "reel")


changed = False
pending, reel_todo = [], []
for d in sorted(glob.glob(f"queue/{cid}/*/")):
    meta_p = os.path.join(d, "meta.json")
    if not os.path.exists(meta_p):
        continue
    pub_p = os.path.join(d, "published.json")
    if os.path.exists(pub_p):
        rec = json.load(open(pub_p, encoding="utf-8"))
        meta = json.load(open(meta_p, encoding="utf-8"))
        if (meta.get("reel") and rec.get("media_id") and not rec.get("reel_id") and not rec.get("reel_tried")
                and now - datetime.fromisoformat(rec["published_at"]) < timedelta(hours=3)):
            reel_todo.append((d, meta, rec))
        continue
    if os.path.exists(os.path.join(d, "attempt.json")):
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

failed = False
if not pending:
    print(f"[{cid}] 게시할 대기열 없음")
else:
    d, meta = pending[0]
    images = sorted(glob.glob(os.path.join(d, "[0-9][0-9].jpg")))
    urls = [f"https://raw.githubusercontent.com/{repo}/{branch}/{p.replace(os.sep, '/')}" for p in images]
    caption = open(os.path.join(d, "caption.txt"), encoding="utf-8").read()
    print(f"[{cid}] 게시: {meta['id']} {meta['topic']} ({len(urls)}장, 릴스 {'O' if meta.get('reel') else 'X'})")
    reel = build_reel(d, images, meta) if meta.get("reel") else None
    if dry:
        print("DRY_RUN — 실제 게시 안 함", urls[:2])
    else:
        att = os.path.join(d, "attempt.json")
        json.dump({"started_at": now.isoformat()}, open(att, "w", encoding="utf-8"))
        changed = True
        record = None
        dup = already_on_instagram(caption)     # 기록이 저장 안 됐던 경우 대비: 이미 올라가 있으면 다시 안 올림
        if dup:
            print(f"[{cid}] 이미 인스타에 같은 게시물이 있음({dup}) → 다시 올리지 않고 완료로 기록")
            record = {"media_id": dup, "published_at": now.isoformat(), "note": "이미 게시돼 있었음"}
        else:
            try:
                record = {"media_id": publish_carousel(urls, caption), "published_at": now.isoformat()}
            except Exception as e:
                err = "".join(traceback.format_exception(e))[-1500:]
                print(f"[{cid}] 게시 중 오류:\n{err}")
                mid = already_on_instagram(caption)
                json.dump({"started_at": now.isoformat(), "error": err, "found_on_instagram": mid},
                          open(att, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
                if mid:
                    print(f"[{cid}] 오류가 났지만 인스타에는 올라가 있음({mid}) → 게시 완료로 보고 릴스도 진행")
                    record = {"media_id": mid, "published_at": now.isoformat(), "note": "오류 후 확인"}
                else:
                    failed = True
        if record and reel:
            rid = post_reel(reel, caption, len(images), meta["id"])
            if rid:
                record["reel_id"] = rid
            else:
                record["reel_tried"] = True
            tg_short(reel, d, meta, rid)
        if record:
            json.dump(record, open(os.path.join(d, "published.json"), "w", encoding="utf-8"))
    if len(pending) > 1:
        print(f"[{cid}] 남은 대기 {len(pending) - 1}개 → 다음 실행 때 게시")

# 피드만 올라가고 릴스가 빠진 게시물 → 릴스만 한 번 더(한 실행에 1개)
if reel_todo and not dry and not failed:
    d, meta, rec = reel_todo[0]
    images = sorted(glob.glob(os.path.join(d, "[0-9][0-9].jpg")))
    caption = open(os.path.join(d, "caption.txt"), encoding="utf-8").read()
    print(f"[{cid}] 빠진 릴스 다시 시도: {meta['id']}")
    rec["reel_tried"] = True
    reel = build_reel(d, images, meta)
    if reel:
        rid = post_reel(reel, caption, len(images), meta["id"])
        if rid:
            rec["reel_id"] = rid
        tg_short(reel, d, meta, rid)
    json.dump(rec, open(os.path.join(d, "published.json"), "w", encoding="utf-8"))
    changed = True

for d in glob.glob(f"queue/{cid}/*/"):
    pj = os.path.join(d, "published.json")
    if os.path.exists(pj):
        t = datetime.fromisoformat(json.load(open(pj))["published_at"])
        if now - t > timedelta(days=5):
            shutil.rmtree(d)
            changed = True
open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a").write(f"changed={'true' if changed else 'false'}\n")
sys.exit(1 if failed else 0)
