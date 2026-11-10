"""Claude로 채널 시각에 맞춰 핫이슈 선정 + 카드뉴스 문구 작성."""
import json
import os
import re

import anthropic

MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")

# 두 채널 공통 — 시각은 달라도 이 선은 절대 넘지 않는다
RULES = """반드시 지킬 규칙 (위반 시 계정 정지·고소 위험)
1. 사실 문장(headline, points)은 제공된 기사 제목·요약에 있는 내용만 쓴다. 숫자·발언·인물 관계를 지어내지 않는다.
2. 발언은 누가 한 말인지 밝힌다. 의혹·주장은 '의혹', '주장'으로 표기하고 단정하지 않는다.
3. 계정의 의견은 comment(한줄평)에만 쓴다. 사실 문장에 의견을 섞지 않는다.
4. 금지: 욕설·멸칭(빨갱이, 수꼴, 좌좀, 틀딱 등), 지역·국적·성별·성소수자·장애인 등 집단 혐오, 부정선거 등 근거 없는 음모론, 폭력 선동, 확인되지 않은 혐의의 단정.
5. 개인 실명 + 의혹 기사는 특히 신중히(한국은 사실적시 명예훼손도 처벌).
6. 기사 문장을 베끼지 말고 자기 말로 요약한다.
7. 李·靑·與·野·北 같은 한자 약칭을 쓰지 말고 한글로 쓴다(이 대통령, 청와대, 여당, 야당, 북한).
8. 직함은 현재 기준으로 쓴다. 현직 대통령은 '이재명 대통령', 윤석열은 '윤석열 전 대통령'. 기사에 '윤 대통령'처럼 옛 표현이 있어도 고쳐 쓴다.
9. person은 그 카드 제목의 주인공(행동하거나 발언한 사람)으로 고른다."""

PROMPT = """아래는 최근 24시간 정치 기사 목록이다(형식: [번호] 매체 | 제목 | 요약).

{articles}

photo_queries: 대통령·총리·장관 등 정부 공식 행사와 관련된 이슈일 때만, 정부 공식 사진 검색용 짧은 키워드를 한국어 1개·영어 1개 넣는다(예: ["대통령 소방의 날", "President Fire Day"]). 국회·정당 이슈처럼 정부 행사가 아니면 [].

이 계정의 시각에서 오늘 다룰 이슈 {n}개를 골라 아래 JSON만 출력해라. 다른 말은 쓰지 마라.
{{
  "cover_title": "표지 한 줄(18자 이내, 오늘 가장 큰 이슈를 강하게)",
  "cover_person": "표지 인물 실명 또는 null",
  "stories": [
    {{
      "tag": "다음 중 하나: 국회, 여당, 야당, 대통령실, 사법, 외교, 안보, 경제, 부동산, 예산, 지방, 선거",
      "headline": "강한 제목(22자 이내, 사실 기반)",
      "person": "중심 인물 실명(기사 표기 그대로) 또는 null",
      "photo_queries": ["한국어 검색어", "English query"],
      "points": ["핵심 사실 1(32자 이내)", "핵심 사실 2(32자 이내)", "핵심 사실 3(32자 이내)"],
      "comment": "계정 시각의 강한 논평(35~55자, 2문장까지. [한줄평 어조] 따를 것. 규칙 4·5 준수)",
      "reel_comment": "릴스 내레이션용 논평(80~120자, 2~3문장, [릴스 어조] 따를 것. 말하듯 자연스럽게, 규칙 4·5 준수)",
      "sources": ["근거 매체명들"],
      "article_ids": [근거 기사 번호들]
    }}
  ],
  "caption_hook": "캡션 첫 줄(질문형 또는 강한 한 문장, 40자 이내)",
  "reel_hook": "릴스 첫 화면·첫 내레이션 한 문장(25자 이내, 시청자를 붙잡는 강한 질문이나 외침)",
  "hashtags": ["#태그", "...총 6~9개, 계정 시각에 맞게"]
}}"""


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("JSON 응답을 찾지 못함:\n" + text[:500])
    return json.loads(m.group(0))


def build_content(articles: list[dict], channel: dict, n: int = 5,
                  recent: list[str] | None = None) -> dict:
    lines = [f"[{i}] {a['source']} | {a['title']} | {a['summary'][:200]}"
             for i, a in enumerate(articles)]
    if recent:
        lines.append("\n최근 며칠간 이미 올린 제목(새 전개가 없으면 같은 이슈는 피할 것):")
        lines += [f"- {h}" for h in recent]
    system = (f"너는 인스타그램 정치 카드뉴스 편집자다.\n\n[계정 시각]\n{channel['viewpoint']}\n\n"
              f"[한줄평 어조]\n{channel.get('comment_style', '')}\n"
              f"[릴스 어조]\n{channel.get('reel_style', channel.get('comment_style', ''))}\n"
              "세게 쓰되, 특정인의 범죄를 사실처럼 단정하지 말고 의견·반문 형태로 쓴다.\n\n" + RULES)
    msg = anthropic.Anthropic().messages.create(
        model=MODEL, max_tokens=8000, system=system,
        messages=[{"role": "user", "content": PROMPT.format(articles="\n".join(lines), n=n)}])
    # 응답에 '생각(thinking)' 블록이 먼저 올 수 있으므로 텍스트 블록만 모은다
    text = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text")
    if not text:
        raise RuntimeError(f"텍스트 응답 없음 (stop_reason={getattr(msg, 'stop_reason', None)})")
    data = _extract_json(text)
    for s in data["stories"]:
        s["links"] = [articles[i]["link"] for i in s.get("article_ids", [])
                      if isinstance(i, int) and 0 <= i < len(articles)][:2]
    data["hashtags"] = list(dict.fromkeys(channel.get("base_hashtags", []) + data.get("hashtags", [])))
    return data
