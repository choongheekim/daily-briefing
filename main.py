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
    cr = c.get("photo_credits") or []
    if cr:
        lines += ["", "📷 사진"] + [f"· {x}" for x in cr]
        if any("Pexels" in x for x in cr):
            lines.append("· Photos provided by Pexels (pexels.com)")
        if any("-SA" in x for x in cr):
            lines.append("· CC BY-SA 사진을 쓴 카드는 같은 CC BY-SA 라이선스로 공개합니다.")
    lines += ["", "※ 언론 보도를 AI가 요약했습니다. 한줄평은 이 계정의 의견입니다.",
              "", " ".join(c.get("hashtags", [])[:12])]
    return "\n".join(lines)[:2200]


def history_path(cid: str) -> str:
    return f"history_{cid}.json"


def write_content(cid: str, out_dir: str) -> dict:
    """기사 수집 → Claude로 문구 작성 → content.json 저장(이미지는 안 만듦)."""
    ch = load_channel(cid)
    hp = history_path(cid)
    history = json.load(open(hp, encoding="utf-8")) if os.path.exists(hp) else []
    recent = [h for d in history[-3:] for h in d["headlines"]]
    articles = fetch_articles(ch["feeds"])
    if len(articles) < 10:
        raise SystemExit(f"기사가 너무 적음({len(articles)}건) — 중단")
    content = build_content(articles, ch, n=int(os.getenv("STORY_COUNT", "5")), recent=recent)
    content = sanitize(content)
    os.makedirs(out_dir, exist_ok=True)
    with open(f"{out_dir}/content.json", "w", encoding="utf-8") as f:
        json.dump(content, f, ensure_ascii=False, indent=2)
    return content


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", required=True, choices=["right", "left"])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--write-only", action="store_true", help="문구(content.json)만 작성 — 회사 PC용")
    ap.add_argument("--from-saved", action="store_true", help="저장된 문구로 이미지·릴스만 — GitHub Actions용")
    args = ap.parse_args()
    args.dry_run = args.dry_run or os.getenv("DRY_RUN") == "true"

    ch = load_channel(args.channel)
    if os.getenv("IG_HANDLE"):
        ch["handle"] = os.environ["IG_HANDLE"]
    set_theme(ch)

    today = os.getenv("POST_DATE") or datetime.now(KST).strftime("%Y-%m-%d")
    out_dir = f"posts/{args.channel}/{today}"
    saved = f"{out_dir}/content.json"

    if args.write_only:
        write_content(args.channel, out_dir)
        print(f"[{args.channel}] 문구 저장 → {saved}")
        return

    if args.from_saved:
        if not os.path.exists(saved) and args.dry_run:   # 테스트: 가장 최근 문구로 대신
            import glob
            prev = sorted(glob.glob(f"posts/{args.channel}/*/content.json"))
            if prev:
                print(f"[테스트] 오늘 문구가 없어 {prev[-1]} 로 대신 그림")
                os.makedirs(out_dir, exist_ok=True)
                import shutil
                shutil.copy(prev[-1], saved)
        if not os.path.exists(saved):
            print(f"[{args.channel}] 오늘 문구({saved})가 없음 → 게시 건너뜀")
            raise SystemExit(3)
        content = json.load(open(saved, encoding="utf-8"))
    elif args.dry_run and os.path.exists(saved) and os.getenv("FRESH") != "1":
        print("[테스트] 오늘 만든 문구 재사용(Claude 호출 안 함)")
        content = json.load(open(saved, encoding="utf-8"))
    else:
        content = write_content(args.channel, out_dir)

    content = sanitize(content)   # 캡션도 같은 표기로
    paths = render_all(content, out_dir)
    caption = make_caption(content)
    with open(f"{out_dir}/caption.txt", "w", encoding="utf-8") as f:
        f.write(caption)
    with open(saved, "w", encoding="utf-8") as f:
        json.dump(content, f, ensure_ascii=False, indent=2)
    print(caption)

    if os.getenv("REELS", "1") == "1":
        try:
            from bot.reels import build_reel, reel_caption
            from bot.render import pick_photo
            used = []

            def pick_rec(*a):
                r = pick_photo(*a)
                if r and r[1]:
                    used.append(r[1].replace("사진: ", ""))
                return r
            build_reel(content, args.channel, out_dir, pick_rec)
            import shutil
            shutil.rmtree(f"{out_dir}/_reel", ignore_errors=True)   # 중간 파일 정리
            rcap = reel_caption(content)
            used = list(dict.fromkeys(used))
            if used:
                extra = "\n\n📷 사진\n" + "\n".join(f"· {x}" for x in used)
                if any("Pexels" in x for x in used):
                    extra += "\n· Photos provided by Pexels (pexels.com)"
                if any("-SA" in x for x in used):
                    extra += "\n· CC BY-SA 사진이 쓰인 영상은 같은 CC BY-SA 라이선스로 공개합니다."
                rcap = (rcap + extra)[:2200]
            with open(f"{out_dir}/reel_caption.txt", "w", encoding="utf-8") as f:
                f.write(rcap)
        except Exception as e:  # 릴스가 실패해도 카드 게시는 진행
            print(f"[reels] 생성 실패: {e}")
    print(f"[{args.channel}] 이미지 {len(paths)}장 → {out_dir}" + (" (dry-run)" if args.dry_run else ""))


if __name__ == "__main__":
    main()
