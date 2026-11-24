"""[회사 PC] 정치 카드뉴스 만들기 → GitHub 대기열(queue/<채널>/<id>/)에 올리기. (hottopic-zip 방식)

사용법:
  py pc\\run.py --slot 07:17                 예약 실행(두 계정 모두, 그 시간에 GitHub이 게시)
  py pc\\run.py --slot now                   지금 바로 게시(올리면 몇 분 안에 GitHub이 게시)
  py pc\\run.py --slot now --test            테스트: GitHub에 안 올리고 out_test 폴더에 카드만 만듦
  py pc\\run.py --slot now --channel right   한 계정만

글쓰기·사실 확인·사진 고르기는 이 PC의 Claude Code(claude -p, 구독 로그인)로 한다 → Claude API 요금 0원.
"""
import nowindow  # noqa: F401  윈도우 검은 창 안 뜨게 (가장 먼저)
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

from buzz import commons, pexels, poster, poster_d  # noqa: E402
from pc import prompts  # noqa: E402

KST = timezone(timedelta(hours=9))
SLOTS = {"07:17": "아침 — 밤사이·오늘 아침 가장 큰 정치 이슈",
         "10:47": "오전 — 오전 회의·발표에서 새로 나온 이슈(오늘 앞서 다룬 주제와 다른 것)",
         "12:30": "점심 — 오전에 새로 나온 이슈·진전",
         "15:47": "오후 — 오후 들어 새로 불붙은 쟁점(오늘 앞서 다룬 주제와 다른 것)",
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


def _ensure_pkgs():
    """쇼츠 만들기에 필요한 무료 패키지(목소리 edge-tts, 영상 도구 imageio-ffmpeg)를 처음 한 번 자동 설치"""
    need = []
    for mod, pkg in (("edge_tts", "edge-tts"), ("imageio_ffmpeg", "imageio-ffmpeg"), ("requests", "requests")):
        try:
            __import__(mod)
        except ImportError:
            need.append(pkg)
    if need:
        log(f"쇼츠용 패키지 설치: {need}")
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", *need], check=False)


def send_short(cid, qdir):
    """PC에서 쇼츠 영상을 만들어 텔레그램으로 보냄(유튜브는 사람이 직접 올림). 실패해도 게시에는 영향 없음."""
    tok, chat = os.getenv("TELEGRAM_BOT_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", "")
    if not tok or not chat:
        log("텔레그램 설정(config.txt) 없음 → 쇼츠 전송 건너뜀")
        return
    try:
        _ensure_pkgs()
        import glob
        import html
        import importlib
        import tempfile
        import requests
        sys.path.insert(0, os.path.join(ROOT, "buzz"))
        import reel_d
        importlib.reload(reel_d)
        from buzz import reel_s
        content = json.load(open(os.path.join(qdir, "content.json"), encoding="utf-8"))
        for card in content["cards"]:
            ph = card.get("photo")
            if ph and ph.get("path"):
                ph["path"] = os.path.join(qdir, ph["path"])
        content.setdefault("channel", cid)
        meta = json.load(open(os.path.join(qdir, "meta.json"), encoding="utf-8"))
        t0 = time.time()
        os.makedirs(os.path.join(ROOT, "work"), exist_ok=True)
        mp4 = os.path.join(ROOT, "work", f"short_{cid}_{meta['id']}.mp4")
        reel_s.build(content, mp4, tempfile.mkdtemp())
        log(f"[{cid}] 쇼츠 만듦({time.time() - t0:.0f}초)")
        cap = open(os.path.join(qdir, "caption.txt"), encoding="utf-8").read()
        body = cap.split("\n\n#")[0].strip().replace("한마디는 이 계정의 의견", "한마디는 이 채널의 의견")
        tags = [t for t in cap.split() if t.startswith("#")][:10]
        desc = body + "\n\n" + " ".join([t for t in tags if t not in ("#카드뉴스",)][:4] + ["#shorts"])
        rs = content.get("reel") or {}
        title = (rs.get("yt_title") or meta.get("topic", ""))[:88] + " #shorts"
        comment = rs.get("comment") or "여러분의 생각은 어떠신가요? 댓글로 남겨 주세요 👇"
        name = "보수의 아침" if cid == "right" else "진보의 아침"
        at = meta.get("publish_at", "")[11:16]
        api = f"https://api.telegram.org/bot{tok}"
        with open(mp4, "rb") as f:
            r = requests.post(f"{api}/sendVideo", timeout=300,
                              files={"video": (os.path.basename(mp4), f, "video/mp4")},
                              data={"chat_id": chat, "supports_streaming": "true", "width": 1080, "height": 1920,
                                    "caption": f"🎬 [{name}] 쇼츠 (인스타 게시 {at})\n"
                                               f"아래 제목·설명을 눌러 복사해서 유튜브에 올리세요."})
        if not r.ok:
            raise RuntimeError(f"영상 보내기 실패 {r.status_code}: {r.text[:200]}")
        tagline = ", ".join(dict.fromkeys([name.replace(" ", ""), name] + [t.lstrip("#") for t in tags]))[:450]
        for label, text in (("📌 제목", title), ("📝 설명", desc[:3500]), ("🏷 태그 (유튜브 '태그' 칸에 붙여넣기)", tagline),
                            ("💬 고정 댓글 (올린 뒤 댓글로 달고 '고정')", comment)):
            requests.post(f"{api}/sendMessage", timeout=60, data={
                "chat_id": chat, "parse_mode": "HTML", "text": f"{label}\n<code>{html.escape(text)}</code>"})
        log(f"[{cid}] 텔레그램으로 쇼츠 보냄")
    except Exception as e:
        log(f"[{cid}] 쇼츠 텔레그램 전송 실패: {e}")


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


def naver_hot():
    """네이버 뉴스 '댓글 많은 뉴스'·'많이 본 뉴스' 제목 — 사람들이 실제로 화내고 클릭하는 주제의 지표"""
    import html as _h
    import requests
    out = []
    for url, tag in (("https://news.naver.com/main/ranking/popularMemo.naver", "댓글많은"),
                     ("https://news.naver.com/main/ranking/popularDay.naver", "많이본")):
        try:
            r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
            txt = r.content.decode("cp949", errors="ignore")
            for t in re.findall(r'class="list_title[^"]*"[^>]*>([^<]+)<', txt):
                t = _h.unescape(t.strip())
                if t and t not in [x[1] for x in out]:
                    out.append((tag, t))
        except Exception as e:
            log(f"네이버 랭킹 수집 실패({tag}): {e}")
    return out


def candidates_text(ch):
    hot = naver_hot()
    hot_txt = "\n".join(f"- ({tag}) {t}" for tag, t in hot[:70])
    return (("[1순위 후보 — 지금 네이버에서 댓글이 가장 많이 달리고 가장 많이 본 기사(분노·논란 지표). 여기서 정치·사회 이슈를 고를 것]\n"
             + hot_txt + "\n\n[참고 — 이 계정이 주로 보는 매체 정치면]\n") if hot else "") + _feed_candidates(ch)


def _feed_candidates(ch):
    from bot.news import fetch_articles
    try:
        arts = fetch_articles(ch["feeds"], hours=18, per_feed=25)
    except Exception as e:
        log(f"기사 수집 실패: {e}")
        arts = []
    lines = [f"- [{a['source']}] {a['title']}" + (f" — {a['summary'][:80]}" if a.get("summary") else "") for a in arts]
    return "\n".join(lines[:50]) or "(후보 수집 실패 — 직접 검색해서 오늘 주요 정치 기사를 찾을 것)"


def example_text():
    ex = json.load(open(os.path.join(ROOT, "examples", "politics.json"), encoding="utf-8"))
    return json.dumps({"topic": "이용철 법무부 장관 후보자와 공소취소 논란", "code": ex["code"], "category": "국회 · 인사청문",
                       "cards": ex["cards"], "caption": "…", "hashtags": ["#…"],
                       "reel": {"hook": "…", "lines": [{"say": "…", "show": {"type": "word", "label": "…", "text": "…"}}] * 6}},
                      ensure_ascii=False)


def validate(post):
    cards = [c for c in post["cards"] if isinstance(c, dict) and c.get("type")]
    covers = [c for c in cards if c["type"] == "cover"]
    outros = [c for c in cards if c["type"] == "outro"]
    KNOWN = ("story", "profile", "timeline", "numbers", "debate")
    odd = [c["type"] for c in cards if c["type"] not in KNOWN + ("cover", "outro")]
    if odd:
        log(f"알 수 없는 카드 종류 제외: {odd}")
    middle = [c for c in cards if c["type"] in KNOWN]
    if not covers or not outros or len(middle) < 3:
        raise ValueError(f"카드 구성이 맞지 않음: {[c.get('type') for c in cards]}")
    if len(middle) > 6:
        middle = middle[:6]
    post["cards"] = [covers[0]] + middle + [outros[-1]]
    if len(cards) != len(post["cards"]):
        log(f"카드 {len(cards)}장 → {len(post['cards'])}장으로 맞춤")
    if not post["cards"][-1].get("opinion"):
        raise ValueError("한줄평(opinion)이 없음")
    out = post["cards"][-1]
    punch = str(out.get("punch") or "").strip()
    if not punch:
        log("경고: 한마디(punch)가 없음 → 한줄평 첫 문장으로 대신")
        punch = re.split(r"(?<=[.!?])\s", out["opinion"].strip())[0][:40]
    out["punch"] = punch[:70]
    reel = post.get("reel") or {}
    lines = []
    for x in (reel.get("lines") or [])[:8]:
        if isinstance(x, dict) and x.get("say"):
            show = x.get("show") if isinstance(x.get("show"), dict) else None
            lines.append({"say": str(x["say"]), "show": show})
        elif isinstance(x, str) and x.strip():
            lines.append({"say": x, "show": None})
    for k, pos in ((1, "1"), (4, "2")):        # 중간 한마디 2번: 의견 장면(화면 전체 채널 색 + 말풍선)으로 고정
        if len(lines) > k:
            sh = lines[k].get("show") or {}
            txt = str(sh.get("text") or "").strip() or lines[k]["say"][:24]
            lines[k]["show"] = {"type": "opinion", "tag": pos, "text": txt}
    post["reel"] = {"hook": reel.get("hook", ""), "lines": lines,
                    "teaser": str(reel.get("teaser") or "").strip()[:30],
                    "yt_title": str(reel.get("yt_title") or "").strip()[:60],
                    "comment": str(reel.get("comment") or "").strip()[:200]}
    txt = json.dumps(post["cards"], ensure_ascii=False)
    if re.search(r"[一-鿿]", txt):
        log("경고: 한자가 섞여 있음 → 그 글자는 카드에서 빠질 수 있음")
    post["code"] = re.sub(r"[^A-Z0-9]", "", post.get("code", "POLITICS").upper())[:10] or "POLITICS"



def _ahash(path):
    """사진 지문(16x16 평균 해시) — 크기가 달라도 같은 사진이면 비슷하게 나온다"""
    try:
        im = Image.open(path).convert("L").resize((16, 16))
        px = list(im.getdata())
        avg = sum(px) / len(px)
        return int("".join("1" if v > avg else "0" for v in px), 2)
    except Exception:
        return None


def _hd(a, b):
    return bin(a ^ b).count("1")


def recent_photo_hashes(cid, n=30):
    """이 계정이 최근 n개 게시물에 쓴 사진들의 지문"""
    out = []
    for d in sorted(glob.glob(os.path.join(ROOT, "queue", cid, "*")))[-n:]:
        for f in glob.glob(os.path.join(d, "photo*.jpg")):
            h = _ahash(f)
            if h is not None:
                out.append(h)
    return out


def drop_repeats(cands, cid, keep=28, need=8, thr=34):
    """최근에 쓴 사진·후보끼리 겹치는 사진을 뒤로 보낸다. 새 사진이 need장 미만일 때만 옛 사진으로 채운다."""
    recent = recent_photo_hashes(cid)
    fresh, stale, seen = [], [], []
    for c in cands:
        h = _ahash(c["path"])
        if h is None:
            continue
        if any(_hd(h, x) <= 8 for x in seen):          # 후보끼리 같은 사진
            continue
        seen.append(h)
        dist = min((_hd(h, x) for x in recent), default=999)
        (stale if dist <= thr else fresh).append((dist, c))
    stale.sort(key=lambda x: -x[0])                      # 덜 비슷한 것부터
    base = [c for _, c in fresh if not c.get("ctx")]
    ctx = [c for _, c in fresh if c.get("ctx")]
    out = base[:keep - 10] + ctx[:10]                    # 맥락 사진 자리를 따로 남겨 둠
    out += [c for c in base[keep - 10:]][:max(0, keep - len(out))]
    if len(out) < need:
        out += [c for _, c in stale][:need - len(out)]
    log(f"사진 중복 걸러냄: 새 사진 {len(fresh)}장 / 최근에 쓴 것과 비슷해서 뺀 것 {len(stale)}장 → 후보 {len(out)}장")
    return out


CTX_MAP = [
    (("국회", "탄핵", "청문회", "법안", "본회의", "의원", "여야"), ["South Korea National Assembly plenary hall", "National Assembly Building Yeouido", "Korean National Assembly hearing"]),
    (("대법원", "법원", "판결", "재판", "선고", "사법부", "법관", "대법관"), ["Supreme Court of Korea building Seocho", "Seoul Central District Court", "Constitutional Court of Korea"]),
    (("대통령실", "청와대", "대통령", "국무회의"), ["Cheong Wa Dae Seoul", "Presidential Office Seoul South Korea", "Korean cabinet meeting"]),
    (("장관", "총리", "정부", "부처", "정책"), ["Government Complex Seoul", "Government Complex Sejong", "Prime Minister of South Korea office"]),
    (("국민의힘", "장동혁", "한동훈", "보수", "윤리위"), ["People Power Party Korea", "People Power Party headquarters Yeouido", "국민의힘 당사"]),
    (("민주당", "더불어민주당", "정청래", "이재명"), ["Democratic Party of Korea headquarters", "더불어민주당 당사", "Democratic Party of Korea press conference"]),
    (("검찰", "법무", "특검", "수사", "공소"), ["Supreme Prosecutors' Office Seoul", "Ministry of Justice Gwacheon", "Seoul Central District Prosecutors Office"]),
    (("국방", "군용기", "미사일", "북한", "KADIZ", "러시아", "경계경보"), ["Ministry of National Defense South Korea", "Republic of Korea Air Force", "Korean demilitarized zone"]),
    (("증시", "코스피", "금리", "환율", "경제"), ["Korea Exchange Seoul", "Bank of Korea headquarters", "KOSPI trading floor"]),
    (("수능", "교육", "입시", "대입"), ["Suneung exam South Korea", "Ministry of Education Sejong", "Korean high school exam"]),
]


def context_queries(post, maxq=5):
    txt = json.dumps({"t": post.get("topic"), "c": post.get("cards")}, ensure_ascii=False)
    scored = sorted(((sum(txt.count(k) for k in keys), qs) for keys, qs in CTX_MAP), key=lambda x: -x[0])
    out = []
    for sc, qs in scored:
        if sc > 0:
            out += qs
    return list(dict.fromkeys(out))[:maxq]


def gather_photos(post, work, cid=None):
    queries = []
    for c in post["cards"]:
        q = c.get("photo_query")
        if q and q not in queries:
            queries.append(q)
    cands, seen = [], set()
    # ① 위키백과 문서 사진(그 인물·기관이 확실한 사진)을 먼저
    subjects = []
    for c in post["cards"]:
        for sj in (c.get("photo_subject") or "").split("|"):
            sj = sj.strip()
            if sj and sj not in subjects:
                subjects.append(sj)
    for sj in subjects[:6]:
        try:
            for c in commons.from_wikipedia(sj, limit=4):
                if c["title"] in seen:
                    continue
                seen.add(c["title"])
                path = commons.download(c)
                if path:
                    c["path"] = path
                    cands.append(c)
        except Exception as e:
            log(f"위키백과 사진 찾기 실패({sj}): {e}")
        time.sleep(1)
    n_wiki = len(cands)
    # ② 코리아넷(정부 공식 플리커) 현장 사진 — 오픈버스로 검색
    from buzz import openverse
    for q in queries[:5]:
        try:
            for c in openverse.search(q, limit=5):
                if c["title"] + c["thumb"] in seen:
                    continue
                seen.add(c["title"] + c["thumb"])
                path = openverse.download(c)
                if path:
                    c["path"] = path
                    cands.append(c)
        except Exception as e:
            log(f"코리아넷 사진 찾기 실패({q}): {e}")
        time.sleep(1)
    n_kn = len(cands) - n_wiki
    # ③ 위키미디어 공용 검색
    for q in queries[:7]:
        for c in commons.search(q, limit=5)[:4]:
            if c["title"] in seen or len(cands) >= 34:
                continue
            seen.add(c["title"])
            path = commons.download(c)
            if path:
                c["path"] = path
                cands.append(c)
        time.sleep(1)
    # ④ 맥락 사진: 인물 사진이 없어도 '그 사건의 무대'(국회·법원·청사 등) 사진을 서로 다른 것으로 여러 장 확보
    n_ctx0 = len(cands)
    for q in context_queries(post):
        try:
            for c in commons.search(q, limit=6)[:5]:
                if c["title"] in seen or len(cands) >= 44:
                    continue
                seen.add(c["title"])
                path = commons.download(c)
                if path:
                    c["path"] = path
                    c["ctx"] = True
                    cands.append(c)
        except Exception as e:
            log(f"맥락 사진 찾기 실패({q}): {e}")
        time.sleep(1)
    log(f"맥락 사진(기관·장소) {len(cands) - n_ctx0}장 추가")
    if len(cands) < 4:
        for q in queries[:2]:
            for c in pexels.search(q, 3):
                path = pexels.download(c)
                if path:
                    c["path"] = path
                    cands.append(c)
    if cid:
        cands = drop_repeats(cands, cid)
    log(f"사진 후보 {len(cands)}장 (위키백과 {n_wiki}장, 코리아넷 {n_kn}장)")
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
                      f" — 사진 대상: {c.get('photo_subject')} / 검색어: {c.get('photo_query')}"
                      for i, c in enumerate(post["cards"], 1))
    cand = "\n".join(f"{i}: " + (f"위키백과 '{c['wiki']}' 문서 사진{'(대표 사진)' if c.get('lead') else ''}" if c.get('wiki')
                                 else ('맥락 사진(기관·장소)' if c.get('ctx') else '코리아넷 정부 현장 사진' if c.get('koreanet') else
                                       ('stock(Pexels)' if c.get('stock') else 'wikimedia 검색')))
                     + f" / {c['title'][:70]} / {c.get('desc', '')[:80]}"
                     for i, c in enumerate(cands, 1))
    res = claude_json(prompts.PICK.format(sheet=sheet, topic=post["topic"], cards=cards, cand=cand, n=len(post["cards"])),
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
        card["photo"] = {"path": c["path"], "credit": c["credit"], "title": c.get("title", "")[:80], "mode": "duo" if c.get("stock") else "color",
                         "cy": 0.35 if card["type"] == "cover" else 0.4}
        if c.get("stock"):
            card["photo"]["caption"] = "자료사진"
        used_sa |= c.get("share_alike", False)
        if c["credit"] not in credits:
            credits.append(c["credit"])
    return credits, used_sa


def caption_text(post, ch, credits, used_sa):
    cap = post["caption"].strip()
    o = post["cards"][-1]
    cap += f"\n\n💬 {ch['label_short']}의 한마디\n“{o['punch']}”\n{o['opinion']}"
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
    cap += "\n※ 언론 보도를 AI가 정리했어요. 한마디는 이 계정의 의견이에요."
    tags = list(dict.fromkeys(post.get("hashtags", [])[:4] + ch.get("base_hashtags", [])[:1]))
    cap += "\n\n" + " ".join(tags[:5])
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

    cands = gather_photos(post, work, cid)
    picks = pick_photos(post, cands, work)
    credits, used_sa = attach(post, cands, picks)
    log(f"[{cid}] 사진 배정: {picks}")

    post_dir = os.path.join(work, "post")
    os.makedirs(post_dir, exist_ok=True)
    json.dump({"date": pub.strftime("%Y-%m-%d"), "code": post["code"], "channel": cid, "cards": post["cards"],
               "reel": post["reel"]},
              open(os.path.join(post_dir, "content.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    images = poster_d.render(post_dir, None, cid)
    open(os.path.join(post_dir, "caption.txt"), "w", encoding="utf-8").write(caption_text(post, ch, credits, used_sa))
    meta = {"id": pid, "channel": cid, "publish_at": pub.isoformat(), "topic": post["topic"],
            "reel": True, "reel_script": post["reel"]}
    json.dump(meta, open(os.path.join(post_dir, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    if test:
        log(f"[{cid}] 테스트 완료 → {post_dir}")
        return post_dir
    dst = os.path.join(ROOT, "queue", cid, pid)
    os.makedirs(dst, exist_ok=True)
    for p in images + [os.path.join(post_dir, n) for n in ("caption.txt", "meta.json", "content.json")]:
        shutil.copy(p, dst)
    # 쇼츠를 만들 때 쓰도록 사진을 줄여서 같이 올리고, 경로는 폴더 안 파일 이름으로 바꾼다
    c = json.load(open(os.path.join(dst, "content.json"), encoding="utf-8"))
    for i, card in enumerate(c["cards"]):
        ph = card.get("photo")
        if ph and ph.get("path"):
            try:
                from PIL import Image
                im = Image.open(ph["path"]).convert("RGB")
                im.thumbnail((1600, 1600))
                im.save(os.path.join(dst, f"photo{i}.jpg"), quality=86)
                ph["path"] = f"photo{i}.jpg"
            except Exception as e:
                log(f"사진 복사 실패: {e}")
                ph.pop("path", None)
    json.dump(c, open(os.path.join(dst, "content.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    h = json.load(open(hist_path(cid), encoding="utf-8")) if os.path.exists(hist_path(cid)) else []
    h.append({"date": pub.strftime("%Y-%m-%d"), "slot": slot, "topic": post["topic"], "id": pid})
    json.dump(h[-200:], open(hist_path(cid), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return dst


# PC에서 고친 프로그램 파일도 같이 올린다(GitHub Actions 가 쇼츠를 만들 때 필요)
DEPLOY = ["buzz/poster_d.py", "buzz/reel_d.py", "buzz/reel_s.py", "buzz/reel.py", "pc/run.py", "pc/prompts.py",
          "publish_queue.py", "buzz/commons.py", "buzz/openverse.py", "bot/publish.py", "pc/short_test.py",
          "buzz/assets/icon_quote.png", "buzz/assets/icon_gavel.png", "buzz/assets/LICENSE-lucide.txt"]


def upload(paths, msg):
    git("config", "user.name", "news-bot-pc")
    git("config", "user.email", "news-bot-pc@users.noreply.github.com")
    git("add", *paths)
    git("add", *[p for p in DEPLOY if os.path.exists(os.path.join(ROOT, p))], check=False)
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
                send_short(cid, out)
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
