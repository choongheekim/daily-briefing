"""채널별 정치 카드뉴스 생성.

사용법
  python main.py --channel right --dry-run
  python main.py --channel left
"""
import argparse
import json
import os
from datetime import datetime

from bot.news import KST, fetch_articles
from bot.render import render_all, sanitize, set_theme
from bot.summarize import build_content


def load_channel(cid: str) -> dict:
    with open(f"channels/{cid}.json", encoding="utf-8") as f:
        return json.load(f)


def make_caption(c: dict) -> str:
    lines = [c["caption_hook"], ""]
    for i, s in enumerate(c["stories"], 1):
        lines.append(f"{i}. {s['headline']}")
        if s.get("comment"):
            lines.append(f"   └ 한줄평: {s['comment']}")
    lines += ["", "📰 출처"]
    for s in c["stories"]:
        lines.append(f"· {', '.join(s.get('sources', []))}")
    lines += ["", "※ 언론 보도를 AI가 요약했습니다. 한줄평은 이 계정의 의견입니다.",
              "", " ".join(c.get("hashtags", [])[:12])]
    return "\n".join(lines)[:2200]


def history_path(cid: str) -> str:
    return f"history_{cid}.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", required=True, choices=["right", "left"])
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    ch = load_channel(args.channel)
    if os.getenv("IG_HANDLE"):
        ch["handle"] = os.environ["IG_HANDLE"]
    set_theme(ch)

    today = datetime.now(KST).strftime("%Y-%m-%d")
    out_dir = f"posts/{args.channel}/{today}"

    hp = history_path(args.channel)
    history = json.load(open(hp, encoding="utf-8")) if os.path.exists(hp) else []
    recent = [h for d in history[-3:] for h in d["headlines"]]

    articles = fetch_articles(ch["feeds"])
    if len(articles) < 10:
        raise SystemExit(f"기사가 너무 적음({len(articles)}건) — 중단")

    content = build_content(articles, ch, n=int(os.getenv("STORY_COUNT", "5")), recent=recent)
    content = sanitize(content)   # 캡션도 같은 표기로
    paths = render_all(content, out_dir)
    caption = make_caption(content)
    with open(f"{out_dir}/caption.txt", "w", encoding="utf-8") as f:
        f.write(caption)
    with open(f"{out_dir}/content.json", "w", encoding="utf-8") as f:
        json.dump(content, f, ensure_ascii=False, indent=2)
    print(caption)

    if os.getenv("REELS", "1") == "1":
        try:
            from bot.reels import build_reel, reel_caption
            from bot.render import pick_photo
            build_reel(content, args.channel, out_dir, pick_photo)
            import shutil
            shutil.rmtree(f"{out_dir}/_reel", ignore_errors=True)   # 중간 파일 정리
            with open(f"{out_dir}/reel_caption.txt", "w", encoding="utf-8") as f:
                f.write(reel_caption(content))
        except Exception as e:  # 릴스가 실패해도 카드 게시는 진행
            print(f"[reels] 생성 실패: {e}")
    print(f"[{args.channel}] 이미지 {len(paths)}장 → {out_dir}" + (" (dry-run)" if args.dry_run else ""))


if __name__ == "__main__":
    main()
