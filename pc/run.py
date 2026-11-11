"""[회사 PC] 정치 카드뉴스 만들기 → GitHub 대기열(queue/<채널>/<id>/)에 올리기. (hottopic-zip 방식)

사용법:
  py pc\\run.py --slot 07:17                 예약 실행(두 계정 모두, 그 시간에 GitHub이 게시)
  py pc\\run.py --slot now                   지금 바로 게시(올리면 몇 분 안에 GitHub이 게시)
  py pc\\run.py --slot now --test            테스트: GitHub에 안 올리고 out_test 폴더에 카드만 만듦
  py pc\\run.py --slot now --channel right   한 계정만

글쓰기·사실 확인·사진 고르기는 이 PC의 Claude Code(claude -p, 구독 로그인)로 한다 → Claude API 요금 0원.
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from buzz import commons, pexels, poster  # noqa: E402
from pc import prompts  # noqa: E402

KST = timezone(timedelta(hours=9))
SLOTS = {"07:17": "아침 — 밤사이·오늘 아침 가장 큰 정치 이슈", "12:30": "점심 — 오전에 새로 나온 이슈·진전",
         "18:30": "저녁 — 오늘 하루 가장 논쟁적이었던 이슈", "now": "지금 가장 화제인 이슈"}
REEL_SLOT = "07:17"                       # 릴스는 아침 게시물에만
LOG = os.path.join(os.path.expanduser("~"), "daily-briefing-logs")

# API로 청구될 수 있는 변수는 이 프로그램 안에서 무조건 제거(구독 사용량으로만 실행)
for _k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
           "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX"):
    os.environ.pop(_k, None)


# ---------- 설정·기록 ----------
def load_config():
    for path in (os.path.join(ROOT, "config.txt"), os.path.join(os.path.expanduser("~"), "daily-briefing-pc.txt")):
        if os.path.exists(path):
            for line in open(path, encoding="utf-8-sig"):
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


def log(msg):
    os.makedirs(LOG, exist_ok=True)
    line = f"[{datetime.now(KST):%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    with open(os.path.join(LOG, f"{datetime.now(KST):%Y-%m-%d}.txt"), "a", encoding="utf-8") as f:
        f.write(line + "\n")


def telegram(msg):
    tok, chat = os.getenv("TELEGRAM_BOT_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", "")
    if not tok or not chat:
        return
    try:
        import requests
        requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", timeout=20,
                      data={"chat_id": chat, "text": f"[정치계정] {msg}"[:3900]})
    except Exception:
        pass


def git(*a, check=True):
    r = subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (r.stdout + r.stderr).strip()
    if out:
        log("git " + a[0] + ": " + out[-500:])
    if check and r.returncode:
        raise RuntimeError(f"git {' '.join(a)} 실패({r.returncode})")
    return r


# ---------- Claude Code 호출 (구독 사용량, API 요금 없음) ----------
def claude(prompt: str, tools: str, max_turns: int = 40, timeout: int = 1500) -> str:
    exe = shutil.which("claude") or shutil.which("claude.cmd")
    if not exe:
        raise RuntimeError("claude 명령을 찾을 수 없어요. Claude Code가 설치·로그인돼 있는지 확인하세요.")
    env = dict(os.environ)
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        env.pop(k, None)
    cmd = [exe, "-p", "--output-format", "json", "--model", os.getenv("CLAUDE_MODEL", "sonnet"),
           "--allowedTools", tools, "--max-turns", str(max_turns)]
    r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8",
                       env=env, cwd=ROOT, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"claude 실행 실패({r.returncode}): {(r.stderr or r.stdout)[-800:]}")
    out = json.loads(r.stdout)
    if out.get("is_error"):
        raise RuntimeError(f"claude 오류: {str(out)[:800]}")
    return out.get("result", "")


def parse_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    s, e = text.find("{"), text.rfind("}")
    return json.loads(text[s:e + 1])


def claude_json(prompt: str, tools: str, **kw) -> dict:
    """JSON이 따옴표 실수 등으로 깨졌으면 '형식만 고쳐서 다시 출력'을 한 번 더 요청(검색 없이)."""
    text = claude(prompt, tools=tools, **kw)
    try:
        return parse_json(text)
    except json.JSONDecodeError as e:
        log(f"JSON 형식 오류({e}) → 형식만 고쳐 달라고 다시 요청")
        fixed = claude("아래 텍스트는 JSON인데 문법 오류가 있습니다(" + str(e) + "). 내용은 그대로 두고, "
                       "문자열 안의 큰따옴표(\")는 ‘ ’ 로 바꾸는 식으로 문법만 고쳐서 올바른 JSON 하나만 출력하세요. "
                       "설명 없이 JSON만.\n\n" + text, tools="Read", max_turns=3, timeout=600)
        return parse_json(fixed)


# ---------- 단계 ----------
def hist_path(cid):
    return os.path.join(ROOT, f"queue_history_{cid}.json")


def history(cid, days=7):
    p = hist_path(cid)
    h = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []
    cut = (datetime.now(KST) - timedelta(days=days)).strftime("%Y-%m-%d")
    return [x for x in h if x["date"] >= cut]


def candidates_text(ch):
    from bot.news import fetch_articles
    try:
        arts = fetch_articles(ch["feeds"], hours=18, per_feed=25)
    except Exception as e:
        log(f"기사 수집 실패: {e}")
        arts = []
    lines = [f"- [{a['source']}] {a['title']}" + (f" — {a['summary'][:80]}" if a.get("summary") else "") for a in arts]
    return "\n".join(lines[:90]) or "(후보 수집 실패 — 직접 검색해서 오늘 주요 정치 기사를 찾을 것)"


def example_text():
    ex = json.load(open(os.path.join(ROOT, "examples", "politics.json"), encoding="utf-8"))
    return json.dumps({"topic": "이용철 법무부 장관 후보자와 공소취소 논란", "code": ex["code"], "category": "국회 · 인사청문",
                       "cards": ex["cards"], "caption": "…", "hashtags": ["#…"],
                       "reel": {"hook": "…", "lines": ["…"] * len(ex["cards"])}}, ensure_ascii=False)


def validate(post):
    cards = [c for c in post["cards"] if isinstance(c, dict) and c.get("type")]
    covers = [c for c in cards if c["type"] == "cover"]
    outros = [c for c in cards if c["type"] == "outro"]
    middle = [c for c in cards if c["type"] not in ("cover", "outro")]
    if not covers or not outros or len(middle) < 3:
        raise ValueError(f"카드 구성이 맞지 않음: {[c.get('type') for c in cards]}")
    if len(middle) > 6:
        middle = middle[:6]
    post["cards"] = [covers[0]] + middle + [outros[-1]]
    if len(cards) != len(post["cards"]):
        log(f"카드 {len(cards)}장 → {len(post['cards'])}장으로 맞춤")
    if not post["cards"][-1].get("opinion"):
        raise ValueError("한줄평(opinion)이 없음")
    reel = post.get("reel") or {}
    lines = [str(x) for x in reel.get("lines", [])][: len(post["cards"])]
    while len(lines) < len(post["cards"]):
        lines.append("")
    post["reel"] = {"hook": reel.get("hook", ""), "lines": lines}
    txt = json.dumps(post["cards"], ensure_ascii=False)
    if re.search(r"[一-鿿]", txt):
        log("경고: 한자가 섞여 있음 → 그 글자는 카드에서 빠질 수 있음")
    post["code"] = re.sub(r"[^A-Z0-9]", "", post.get("code", "POLITICS").upper())[:10] or "POLITICS"


def gather_photos(post, work):
    queries = []
    for c in post["cards"]:
        q = c.get("photo_query")
        if q and q not in queries:
            queries.append(q)
    cands, seen = [], set()
    for q in queries[:7]:
        for c in commons.search(q, limit=5)[:4]:
            if c["title"] in seen or len(cands) >= 20:
                continue
            seen.add(c["title"])
            path = commons.download(c)
            if path:
                c["path"] = path
                cands.append(c)
        time.sleep(1)
    if len(cands) < 4:
        for q in queries[:2]:
            for c in pexels.search(q, 3):
                path = pexels.download(c)
                if path:
                    c["path"] = path
                    cands.append(c)
    log(f"사진 후보 {len(cands)}장")
    return cands


def contact_sheet(cands, path):
    cols, tw, th = 4, 420, 420
    rows = (len(cands) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw, rows * (th + 40)), "white")
    d = ImageDraw.Draw(sheet)
    f = ImageFont.truetype(os.path.join(ROOT, "fonts", "Pretendard-ExtraBold.otf"), 34)
    f2 = ImageFont.truetype(os.path.join(ROOT, "fonts", "Pretendard-Medium.otf"), 20)
    for i, c in enumerate(cands, 1):
        im = Image.open(c["path"]).convert("RGB")
        im.thumbnail((tw - 10, th - 10))
        x, y = ((i - 1) % cols) * tw, ((i - 1) // cols) * (th + 40)
        sheet.paste(im, (x + 5, y + 5))
        d.rectangle((x + 5, y + 5, x + 70, y + 50), fill="red")
        d.text((x + 14, y + 8), str(i), font=f, fill="white")
        d.text((x + 8, y + th + 2), ("stock " if c.get("stock") else "") + c["title"][5:40], font=f2, fill="black")
    sheet.save(path, quality=85)


def pick_photos(post, cands, work):
    if not cands:
        return {}
    sheet = os.path.join(work, "photo_candidates.jpg")
    contact_sheet(cands, sheet)
    cards = "\n".join(f"{i}. [{c['type']}] {c.get('title') if isinstance(c.get('title'), str) else ' '.join(c.get('title', []))}"
                      f" — 사진 검색어: {c.get('photo_query')}" for i, c in enumerate(post["cards"], 1))
    cand = "\n".join(f"{i}: {'stock(Pexels)' if c.get('stock') else 'wikimedia'} / {c['title'][:70]} / {c.get('desc', '')[:80]}"
                     for i, c in enumerate(cands, 1))
    res = claude_json(prompts.PICK.format(sheet=sheet, topic=post["topic"], cards=cards, cand=cand),
                      tools="Read", max_turns=6, timeout=600)
    return {int(k): int(v) for k, v in res.items() if v}


def attach(post, cands, picks):
    used_sa, credits, taken = False, [], set()
    for i, card in enumerate(post["cards"], 1):
        n = picks.get(i)
        if not n or n > len(cands) or n in taken:
            continue
        taken.add(n)
        c = cands[n - 1]
        card["photo"] = {"path": c["path"], "credit": c["credit"], "mode": "duo" if c.get("stock") else "color",
                         "cy": 0.35 if card["type"] == "cover" else 0.4}
        if c.get("stock"):
            card["photo"]["caption"] = "자료사진"
        used_sa |= c.get("share_alike", False)
        if c["credit"] not in credits:
            credits.append(c["credit"])
    return credits, used_sa


def caption_text(post, ch, credits, used_sa):
    cap = post["caption"].strip()
    cap += f"\n\n💬 {ch['label_short']}의 한줄평\n{post['cards'][-1]['opinion']}"
    srcs = []
    for c in post["cards"]:
        for s in c.get("sources", []):
            if s not in srcs:
                srcs.append(s)
    if srcs:
        cap += "\n\n출처: " + ", ".join(srcs[:10])
    if credits:
        cap += "\n📷 " + " · ".join(credits)
        if used_sa:
            cap += "\n(사진이 CC BY-SA 라이선스라 이 게시물 이미지도 같은 조건으로 공유할 수 있어요.)"
    cap += "\n※ 언론 보도를 AI가 정리했어요. 한줄평은 이 계정의 의견이에요."
    tags = list(dict.fromkeys(ch.get("base_hashtags", []) + post.get("hashtags", [])))
    cap += "\n\n" + " ".join(tags[:14])
    return cap[:2150]


def publish_time(slot):
    now = datetime.now(KST)
    if slot == "now":
        return now
    h, m = map(int, slot.split(":"))
    t = now.replace(hour=h, minute=m, second=0, microsecond=0)
    return t if t > now - timedelta(minutes=30) else t + timedelta(days=1)


def make_post(cid, slot, test):
    ch = json.load(open(os.path.join(ROOT, "channels", f"{cid}.json"), encoding="utf-8"))
    ch["label_short"] = "보수" if cid == "right" else "진보"
    poster.set_channel(cid)
    pub = publish_time(slot)
    pid = pub.strftime("%Y%m%d-%H%M%S") if slot == "now" else pub.strftime("%Y%m%d-%H%M")
    work = os.path.join(ROOT, "out_test" if test else "work", cid, pid)
    os.makedirs(work, exist_ok=True)
    log(f"=== [{cid}] 시작 {pid} (슬롯 {slot}{', 테스트' if test else ''})")
    hist = history(cid)
    prompt = prompts.WRITE.format(
        handle=poster.CHANNELS[cid]["handle"], now=datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        viewpoint=ch["viewpoint"], comment_style=ch["comment_style"], slot_note=SLOTS.get(slot, SLOTS["now"]),
        history="\n".join(f"- {h['date']} {h['topic']}" for h in hist) or "(없음)",
        candidates=candidates_text(ch), guide=prompts.CARD_GUIDE, example=example_text())
    t0 = time.time()
    post = claude_json(prompt, tools="WebSearch,WebFetch")
    validate(post)
    log(f"[{cid}] 주제: {post['topic']} ({time.time() - t0:.0f}초)")
    t1 = time.time()
    try:
        checked = claude_json(prompts.FACT.format(now=datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
                                                  draft=json.dumps(post, ensure_ascii=False)),
                              tools="WebSearch,WebFetch", max_turns=40)
        validate(checked)
        log(f"[{cid}] 사실 확인 완료({time.time() - t1:.0f}초): {checked.get('fact_notes', [])}")
        post = checked
    except Exception as e:
        raise RuntimeError(f"사실 확인 단계 실패 → 이번 게시물은 건너뜀: {e}")

    cands = gather_photos(post, work)
    picks = pick_photos(post, cands, work)
    credits, used_sa = attach(post, cands, picks)
    log(f"[{cid}] 사진 배정: {picks}")

    post_dir = os.path.join(work, "post")
    os.makedirs(post_dir, exist_ok=True)
    json.dump({"date": pub.strftime("%Y-%m-%d"), "code": post["code"], "cards": post["cards"]},
              open(os.path.join(post_dir, "content.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    images = poster.render(post_dir, "C", None, cid)
    open(os.path.join(post_dir, "caption.txt"), "w", encoding="utf-8").write(caption_text(post, ch, credits, used_sa))
    meta = {"id": pid, "channel": cid, "publish_at": pub.isoformat(), "topic": post["topic"],
            "reel": slot in (REEL_SLOT,) or os.getenv("FORCE_REEL") == "1", "reel_script": post["reel"]}
    json.dump(meta, open(os.path.join(post_dir, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    if test:
        log(f"[{cid}] 테스트 완료 → {post_dir}")
        return post_dir
    dst = os.path.join(ROOT, "queue", cid, pid)
    os.makedirs(dst, exist_ok=True)
    for p in images + [os.path.join(post_dir, n) for n in ("caption.txt", "meta.json", "content.json")]:
        shutil.copy(p, dst)
    # content.json 안의 사진 경로는 PC 경로라 지움(캡션·크레딧은 이미 반영됨)
    c = json.load(open(os.path.join(dst, "content.json"), encoding="utf-8"))
    for card in c["cards"]:
        if card.get("photo"):
            card["photo"].pop("path", None)
    json.dump(c, open(os.path.join(dst, "content.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    h = json.load(open(hist_path(cid), encoding="utf-8")) if os.path.exists(hist_path(cid)) else []
    h.append({"date": pub.strftime("%Y-%m-%d"), "slot": slot, "topic": post["topic"], "id": pid})
    json.dump(h[-200:], open(hist_path(cid), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return dst


def upload(paths, msg):
    git("config", "user.name", "news-bot-pc")
    git("config", "user.email", "news-bot-pc@users.noreply.github.com")
    git("add", *paths)
    c = git("commit", "-qm", msg, check=False)
    if c.returncode and "nothing to commit" not in (c.stdout + c.stderr):
        raise RuntimeError("커밋 실패")
    for i in range(3):
        git("pull", "-q", "--rebase", "--autostash", "-X", "theirs", check=False)
        if git("push", "-q", check=False).returncode == 0:
            return
        time.sleep(20)
    raise RuntimeError("GitHub에 올리기(push) 3번 실패")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", default="now")
    ap.add_argument("--test", action="store_true", help="GitHub에 올리지 않고 out_test 폴더에만 만듦")
    ap.add_argument("--channel", default="all", choices=["all", "right", "left"])
    a = ap.parse_args()
    load_config()
    if not a.test:
        git("pull", "-q", "--rebase", "--autostash", check=False)
    done, failed = [], []
    for cid in (["right", "left"] if a.channel == "all" else [a.channel]):
        try:
            out = make_post(cid, a.slot, a.test)
            done.append(out)
            if not a.test:          # 계정마다 바로 올려서, 한쪽이 실패해도 다른 쪽은 게시되게
                upload([os.path.relpath(out, ROOT), os.path.relpath(hist_path(cid), ROOT)],
                       f"queue {cid} {os.path.basename(out)}")
                log(f"[{cid}] GitHub 대기열에 올림")
        except Exception as e:
            failed.append(cid)
            log(f"[{cid}] 실패: " + "".join(traceback.format_exception(e))[-1500:])
            telegram(f"{cid} 게시물 만들기 실패: {e}")
    if a.test and done and os.name == "nt":
        for d in done:
            subprocess.Popen(["explorer", os.path.abspath(d)])
    log(f"=== 끝: 성공 {len(done)}, 실패 {failed}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
