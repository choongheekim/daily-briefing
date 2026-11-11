"""Claude로 카드뉴스·릴스 문구 작성 — 3단계

1) 선정: 기사 제목·요약 목록에서 오늘 다룰 이슈 N개 선택
2) 작성: 선택된 이슈의 '기사 본문'을 읽고 카드·릴스 문구 작성
3) 검수: 별도 검수자가 본문과 대조해 사실·직함·규칙 위반을 고친 최종본 출력
"""
import json
import os
import re
import time

import anthropic

MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")              # 문구 작성(품질 중요)
LIGHT_MODEL = os.getenv("CLAUDE_LIGHT_MODEL", "claude-haiku-5-5")   # 이슈 선정·검수(저렴)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124 Safari/537.36"}

# 두 채널 공통 — 시각은 달라도 이 선은 절대 넘지 않는다
RULES = """반드시 지킬 규칙 (위반 시 계정 정지·고소 위험)
1. 사실 문장(headline, points)은 제공된 기사 본문·제목에 있는 내용만 쓴다. 숫자·발언·인물 관계를 지어내지 않는다.
2. 발언은 누가 한 말인지 밝힌다. 의혹·주장은 '의혹', '주장'으로 표기하고 단정하지 않는다.
3. 계정의 의견은 comment·reel_comment에만 쓴다. 사실 문장에 의견을 섞지 않는다.
4. 금지: 욕설·멸칭(빨갱이, 수꼴, 좌좀, 틀딱 등), 지역·국적·성별·성소수자·장애인 등 집단 혐오, 부정선거 등 근거 없는 음모론, 폭력 선동, 확인되지 않은 혐의의 단정, 특정 정당·집단 전체를 범죄자로 부르는 표현.
5. 개인 실명 + 의혹 기사는 특히 신중히(한국은 사실적시 명예훼손도 처벌). 의견은 반문·평가 형태로 쓴다.
6. 기사 문장을 그대로 베끼지 말고 자기 말로 요약한다.
7. 李·靑·與·野·北 같은 한자 약칭을 쓰지 말고 한글로 쓴다(이 대통령, 청와대, 여당, 야당, 북한).
8. 직함은 현재 기준: 현직 대통령은 '이재명 대통령', 윤석열은 '윤석열 전 대통령'. 기사에 옛 직함이 있어도 고쳐 쓴다.
9. person은 그 카드 제목의 주인공(행동하거나 발언한 사람)으로 고른다."""

SELECT = """아래는 최근 24시간 정치 기사 목록이다(형식: [번호] 매체 | 제목 | 요약).

{articles}

이 계정의 시각에서 오늘 다룰 이슈 {n}개를 골라라. 같은 사건은 하나로 묶고, 이슈마다 근거 기사 번호를 중요한 순서로 최대 3개 고른다.
아래 JSON만 출력:
{{"stories": [{{"topic": "이슈 한 줄 설명", "article_ids": [번호, 번호]}}]}}"""

WRITE = """오늘 다룰 이슈와 근거 기사 본문이다.

{bundle}

photo_queries: 대통령·총리·장관 등 정부 공식 행사 관련 이슈일 때만 정부 공식 사진 검색용 짧은 키워드를 한국어 1개·영어 1개(예: ["대통령 소방의 날", "President Fire Day"]). 국회·정당 이슈면 [].

위 본문만 근거로, 이 계정의 시각에서 아래 JSON만 출력해라. 다른 말은 쓰지 마라.
{{
  "cover_title": "표지 한 줄(18자 이내, 오늘 가장 큰 이슈를 강하게)",
  "cover_person": "표지 인물 실명 또는 null",
  "reel_hook": "릴스 첫 화면·첫 내레이션 한 문장(25자 이내, 시청자를 붙잡는 강한 질문이나 외침)",
  "stories": [
    {{
      "issue_no": 이슈 번호,
      "tag": "다음 중 하나: 국회, 여당, 야당, 대통령실, 사법, 외교, 안보, 경제, 부동산, 예산, 지방, 선거",
      "headline": "강한 제목(22자 이내, 사실 기반)",
      "person": "제목의 주인공 실명(본문 표기 그대로) 또는 null",
      "photo_queries": ["한국어 검색어", "English query"],
      "points": ["핵심 사실 1(32자 이내, 본문의 구체적 숫자·발언 활용)", "핵심 사실 2(32자 이내)", "핵심 사실 3(32자 이내)"],
      "comment": "카드 한줄평(35~55자, 2문장까지, [한줄평 어조])",
      "reel_comment": "릴스 내레이션 논평(80~120자, 2~3문장, [릴스 어조], 말하듯 자연스럽게)",
      "sources": ["근거 매체명들"]
    }}
  ],
  "caption_hook": "캡션 첫 줄(질문형 또는 강한 한 문장, 40자 이내)",
  "hashtags": ["#태그", "...총 6~9개, 계정 시각에 맞게"]
}}"""

REVIEW = """너는 뉴스 콘텐츠 검수 데스크다. 아래 [초안]을 [근거 본문]과 한 줄씩 대조해 검수하라.

점검 항목
- headline·points의 모든 사실(숫자, 날짜, 발언, 발언자, 직함)이 본문과 일치하는가. 본문에 없는 사실은 삭제하거나 본문 내용으로 고친다.
- 의혹·주장을 사실처럼 단정하지 않았는가.
- 직함·표기 규칙(현직 '이재명 대통령', '윤석열 전 대통령', 한자 약칭 금지)을 지켰는가.
- comment·reel_comment가 규칙 4·5를 어기지 않는가(멸칭, 집단 혐오, 음모론, 폭력 선동, 혐의 단정, 정당 전체를 범죄자로 부르기). 어조의 세기는 유지하되 위반 표현만 바꾼다.
- 글자 수 제한(headline 22자, points 32자, comment 55자, reel_comment 120자)을 지켰는가.
- person이 제목의 주인공인가.

[규칙]
{rules}

[근거 본문]
{bundle}

[초안]
{draft}

같은 JSON 구조로 고친 최종본만 출력하고, 맨 끝에 "review_notes": ["고친 내용 요약", ...] 필드를 추가해라. 다른 말은 쓰지 마라."""


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("JSON 응답을 찾지 못함:\n" + text[:500])
    return json.loads(m.group(0))


# 1M 토큰당 달러 (입력, 출력)
PRICE = {"haiku": (0.10, 0.50), "sonnet": (2.0, 10.0), "opus": (4.0, 20.0)}
USD_KRW = 1450
COST = {"usd": 0.0}


def _log_cost(msg):
    u = getattr(msg, "usage", None)
    if not u:
        return
    pin, pout = next((v for k, v in PRICE.items() if k in msg.model), PRICE["sonnet"])
    usd = u.input_tokens / 1e6 * pin + u.output_tokens / 1e6 * pout
    COST["usd"] += usd
    print(f"[비용] {msg.model} 입력 {u.input_tokens:,} / 출력 {u.output_tokens:,} 토큰 "
          f"≈ {usd * USD_KRW:.0f}원 (누적 {COST['usd'] * USD_KRW:.0f}원)")


def _ask(system: str, user: str, max_tokens: int = 8000, model: str | None = None) -> dict:
    client = anthropic.Anthropic()
    for attempt in range(3):
        try:
            kw = dict(model=model or MODEL, max_tokens=max_tokens, system=system,
                      messages=[{"role": "user", "content": user}])
            try:   # '생각' 토큰은 출력 요금으로 청구되므로 끈다
                msg = client.messages.create(thinking={"type": "disabled"}, **kw)
            except anthropic.BadRequestError:
                msg = client.messages.create(**kw)
            _log_cost(msg)
            # 응답에 '생각(thinking)' 블록이 먼저 올 수 있으므로 텍스트 블록만 모은다
            text = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text")
            if not text:
                raise RuntimeError(f"텍스트 응답 없음 (stop_reason={getattr(msg, 'stop_reason', None)})")
            return _extract_json(text)
        except (ValueError, json.JSONDecodeError) as e:
            print(f"[summarize] JSON 파싱 실패, 재시도 {attempt + 1}: {e}")
            time.sleep(3)
    raise RuntimeError("Claude 응답을 3번 연속 해석하지 못함")


def fetch_body(url: str, limit: int = 1200) -> str:
    """기사 본문 추출(실패하면 빈 문자열)."""
    try:
        import requests
        import trafilatura
        r = requests.get(url, headers=UA, timeout=15)
        r.encoding = r.apparent_encoding if r.encoding in (None, "ISO-8859-1") else r.encoding
        txt = trafilatura.extract(r.text, favor_precision=True) or ""
        return re.sub(r"\n{2,}", "\n", txt)[:limit]
    except Exception as e:
        print(f"[summarize] 본문 수집 실패 {url[:60]}: {e}")
        return ""


def build_content(articles: list[dict], channel: dict, n: int = 5,
                  recent: list[str] | None = None) -> dict:
    system = (f"너는 인스타그램 정치 카드뉴스·릴스 편집자다.\n\n[계정 시각]\n{channel['viewpoint']}\n\n"
              f"[한줄평 어조]\n{channel.get('comment_style', '')}\n"
              f"[릴스 어조]\n{channel.get('reel_style', channel.get('comment_style', ''))}\n"
              "세게 쓰되, 특정인의 범죄를 사실처럼 단정하지 말고 의견·반문 형태로 쓴다.\n\n" + RULES)

    # 1) 선정
    lines = [f"[{i}] {a['source']} | {a['title']} | {a['summary'][:200]}" for i, a in enumerate(articles)]
    if recent:
        lines.append("\n최근 며칠간 이미 올린 제목(새 전개가 없으면 같은 이슈는 피할 것):")
        lines += [f"- {h}" for h in recent]
    picked = _ask(system, SELECT.format(articles="\n".join(lines), n=n), 3000, LIGHT_MODEL)["stories"][:n]

    # 2) 본문 수집
    blocks, issue_meta = [], []
    for k, st in enumerate(picked, 1):
        ids = [i for i in st.get("article_ids", []) if isinstance(i, int) and 0 <= i < len(articles)][:2]
        parts = []
        for i in ids:
            a = articles[i]
            body = fetch_body(a["link"]) or a["summary"]
            parts.append(f"  ({a['source']}) {a['title']}\n  {body}")
        blocks.append(f"[이슈 {k}] {st.get('topic', '')}\n" + "\n\n".join(parts))
        issue_meta.append({"links": [articles[i]["link"] for i in ids][:2],
                           "sources": list(dict.fromkeys(articles[i]["source"] for i in ids))})
    bundle = "\n\n".join(blocks)
    print(f"[summarize] 이슈 {len(picked)}개, 본문 {len(bundle)}자")

    # 3) 작성
    draft = _ask(system, WRITE.format(bundle=bundle))

    # 4) 검수
    try:
        final = _ask(system, REVIEW.format(rules=RULES, bundle=bundle,
                                           draft=json.dumps(draft, ensure_ascii=False, indent=1)),
                     8000, LIGHT_MODEL)
        if not final.get("stories"):
            raise ValueError("검수 결과에 stories 없음")
        for note in final.get("review_notes", []):
            print(f"[검수] {note}")
    except Exception as e:
        print(f"[summarize] 검수 실패, 초안 사용: {e}")
        final = draft

    for k, s in enumerate(final["stories"]):
        try:
            idx = int(s.get("issue_no", k + 1)) - 1
        except (TypeError, ValueError):
            idx = k
        meta = issue_meta[max(0, min(idx, len(issue_meta) - 1))] if issue_meta else {}
        s["links"] = meta.get("links", [])
        if not s.get("sources"):
            s["sources"] = meta.get("sources", [])
    final["hashtags"] = list(dict.fromkeys(channel.get("base_hashtags", []) + final.get("hashtags", [])))
    return final
