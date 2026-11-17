"""텔레그램 쇼츠 전송 시험: 가장 최근 게시물(보수·진보 각 1개)의 쇼츠를 만들어 텔레그램으로 보냄."""
import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pc"))
sys.path.insert(0, ROOT)
import run  # noqa: E402

run.load_config()
for cid in ("right", "left"):
    dirs = sorted(d for d in glob.glob(os.path.join(ROOT, "queue", cid, "*")) if os.path.exists(os.path.join(d, "content.json")))
    if dirs:
        run.send_short(cid, dirs[-1])
print("끝 — 텔레그램을 확인하세요.")
