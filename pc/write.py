"""[회사 PC] 매일 06:40 — 기사 수집 → Claude Code(구독)로 문구 작성 → GitHub에 올리기.

- API 요금 0원: ANTHROPIC_API_KEY 같은 환경변수를 지우고 claude -p 로 호출한다.
- 이미지·릴스·인스타 게시는 07:17 GitHub Actions가 한다(회사망은 facebook.com 차단).
- 실패하면 텔레그램으로 알림(설정 파일에 토큰이 있을 때).

설정 파일(선택): %USERPROFILE%\\daily-briefing-pc.txt
    TELEGRAM_BOT_TOKEN=...
    TELEGRAM_CHAT_ID=...
로그: %USERPROFILE%\\daily-briefing-logs\\날짜.txt
"""
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.path.expanduser("~")
KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).strftime("%Y-%m-%d")
LOG_DIR = os.path.join(HOME, "daily-briefing-logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG = open(os.path.join(LOG_DIR, f"{TODAY}.txt"), "a", encoding="utf-8")

# API로 청구될 수 있는 변수는 이 프로그램 안에서 모두 제거
for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
          "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX"):
    os.environ.pop(k, None)
os.environ["LLM_BACKEND"] = "cli"
os.environ["PYTHONIOENCODING"] = "utf-8"

# 텔레그램 설정 읽기
cfg = os.path.join(HOME, "daily-briefing-pc.txt")
if os.path.exists(cfg):
    for line in open(cfg, encoding="utf-8-sig"):
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def log(msg):
    line = f"{datetime.now(KST):%H:%M:%S} {msg}"
    print(line, flush=True)
    LOG.write(line + "\n")
    LOG.flush()


def run(*cmd, check=True):
    r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (r.stdout + r.stderr).strip()
    if out:
        log(out[-2000:])
    if check and r.returncode:
        raise RuntimeError(f"명령 실패({r.returncode}): {' '.join(cmd)}")
    return r


def notify(text):
    sys.path.insert(0, REPO)
    try:
        from notify import send
        send(text)
    except Exception as e:
        log(f"알림 실패: {e}")


def main():
    os.chdir(REPO)
    sys.path.insert(0, REPO)
    run("git", "pull", "-q", "--rebase", "--autostash")
    key = TODAY
    if "--extra" in sys.argv:   # 오늘 추가 게시: 2026-11-11_2, _3 … (올리면 GitHub이 바로 게시)
        n = 2
        while os.path.exists(f"posts/right/{TODAY}_{n}") or os.path.exists(f"posts/left/{TODAY}_{n}"):
            n += 1
        key = f"{TODAY}_{n}"
    os.environ["POST_DATE"] = key
    log(f"=== 문구 작성 시작 {key} ===")
    done, failed = [], []
    for cid in ("right", "left"):
        path = f"posts/{cid}/{key}/content.json"
        if os.path.exists(path):
            log(f"[{cid}] 이미 있음 → 건너뜀")
            done.append(cid)
            continue
        for attempt in (1, 2):
            r = subprocess.run([sys.executable, "main.py", "--channel", cid, "--write-only"], cwd=REPO,
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            log((r.stdout + r.stderr)[-3000:])
            if r.returncode == 0 and os.path.exists(path):
                done.append(cid)
                break
            log(f"[{cid}] {attempt}차 실패")
            time.sleep(60)
        else:
            failed.append(cid)
    if done:
        run("git", "add", *[f"posts/{c}/{key}/content.json" for c in done])
        run("git", "commit", "-qm", f"문구 {key} (PC)", check=False)
        for attempt in range(3):
            run("git", "pull", "-q", "--rebase", "--autostash", "-X", "theirs", check=False)
            if run("git", "push", "-q", check=False).returncode == 0:
                break
            time.sleep(20)
        else:
            raise RuntimeError("GitHub에 올리기(push) 3번 실패")
    if failed:
        notify(f"⚠️ 회사 PC 문구 작성 실패: {', '.join(failed)} ({key}). 로그: {LOG_DIR}")
    log(f"=== 끝: 성공 {done}, 실패 {failed} ===")
    return 0 if not failed else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log(traceback.format_exc())
        notify(f"❌ 회사 PC 문구 작성 중 오류({TODAY}): {e}")
        sys.exit(1)
