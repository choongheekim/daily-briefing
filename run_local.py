"""PC에서 직접 돌리는 버전 (GitHub 불필요).

1) 뉴스 수집·요약·카드 생성 (main.py와 동일)
2) 카드 이미지를 imgbb에 임시 업로드(1일 후 자동 삭제) → 인스타가 가져갈 공개 주소 확보
3) 인스타 캐러셀 게시 → history 갱신

설정: 같은 폴더의 config.txt (config_예시.txt 참고)
실행: python run_local.py            # 두 계정 모두
      python run_local.py --dry-run  # 카드만 만들고 게시 안 함
      python run_local.py --channel left
"""
import argparse
import base64
import glob
import json
import os
import subprocess
import sys
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)


def load_config(path="config.txt"):
    if not os.path.exists(path):
        sys.exit("config.txt 가 없습니다. config_예시.txt 를 복사해 config.txt 로 저장하고 값을 채우세요.")
    cfg = {}
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip()
    return cfg


def upload_imgbb(path: str, key: str) -> str:
    import requests
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read())
    for i in range(3):
        r = requests.post("https://api.imgbb.com/1/upload",
                          params={"key": key, "expiration": 86400},
                          data={"image": b64}, timeout=120)
        if r.status_code == 200 and r.json().get("success"):
            return r.json()["data"]["url"]
        time.sleep(5 * (i + 1))
    raise RuntimeError(f"imgbb 업로드 실패: {r.status_code} {r.text[:200]}")


def log(msg):
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line)
    with open("run_log.txt", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_channel(cid: str, cfg: dict, dry: bool):
    from bot.news import KST
    env = dict(os.environ)
    env.update({k: v for k, v in cfg.items() if k in ("ANTHROPIC_API_KEY", "FLICKR_API_KEY")})
    # 1) 카드 생성
    r = subprocess.run([sys.executable, "main.py", "--channel", cid], env=env)
    if r.returncode != 0:
        raise RuntimeError("카드 생성 실패")
    if dry:
        return
    today = datetime.now(KST).strftime("%Y-%m-%d")
    out = f"posts/{cid}/{today}"
    images = sorted(glob.glob(f"{out}/*.jpg"))
    caption = open(f"{out}/caption.txt", encoding="utf-8").read()
    content = json.load(open(f"{out}/content.json", encoding="utf-8"))

    # 2) 임시 공개 주소
    urls = [upload_imgbb(p, cfg["IMGBB_API_KEY"]) for p in images]
    log(f"{cid}: 이미지 {len(urls)}장 업로드")

    # 3) 게시
    suffix = "RIGHT" if cid == "right" else "LEFT"
    os.environ["IG_ACCESS_TOKEN"] = cfg[f"IG_ACCESS_TOKEN_{suffix}"]
    os.environ["IG_USER_ID"] = cfg.get(f"IG_USER_ID_{suffix}", "")
    import importlib
    import bot.publish as pub
    importlib.reload(pub)  # 채널별 토큰으로 주소 다시 계산
    media_id = pub.publish_carousel(urls, caption)

    hp = f"history_{cid}.json"
    hist = json.load(open(hp, encoding="utf-8")) if os.path.exists(hp) else []
    hist.append({"date": today, "media_id": media_id,
                 "headlines": [s["headline"] for s in content["stories"]]})
    json.dump(hist[-30:], open(hp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    log(f"{cid}: 게시 완료 {media_id}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", choices=["right", "left", "all"], default="all")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    cfg = load_config()
    for cid in (["right", "left"] if a.channel == "all" else [a.channel]):
        try:
            run_channel(cid, cfg, a.dry_run)
        except Exception as e:  # 한 계정이 실패해도 다른 계정은 진행
            log(f"{cid}: 실패 — {e}")


if __name__ == "__main__":
    main()
