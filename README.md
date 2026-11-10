# 매일 정치 핫이슈 인스타 자동 게시 봇 (보수·진보 2계정)

| 채널 | 설정 파일 | 매체 | 색 |
|---|---|---|---|
| 보수 `right` | `channels/right.json` | 조선·동아·중앙·매경·연합 | 빨강 |
| 진보 `left` | `channels/left.json` | 한겨레·경향·오마이뉴스·연합 | 파랑 |

계정명(`handle`), 표지 라벨, 색, 매체, **시각 설명(viewpoint)** 은 각 json에서 바꾸면 됩니다.
두 채널 모두 같은 안전 규칙(사실만, 한줄평에만 의견, 혐오·멸칭·음모론 금지)을 따릅니다 → `bot/summarize.py`의 `RULES`.

매일 아침 7시 17분(KST)에 아래 과정이 자동으로 돌아갑니다.

1. **수집** — 연합·조선·동아·한겨레·경향 정치 RSS (최근 24시간)
2. **선정·요약** — Claude가 여러 매체가 함께 다룬 핫이슈 5개 선정, 강한 제목 + 사실 3줄
3. **카드 생성** — 1080×1350 카드뉴스 7장 (표지 + 이슈 5 + 마무리)
4. **게시** — Instagram API로 캐러셀 게시, 최근 3일 제목은 중복 회피

## ★ PC에서 돌리기 (GitHub 없이)
1. https://api.imgbb.com 에서 무료 가입 → API 키 발급 (카드 이미지를 인스타가 가져갈 임시 공개 주소, 1일 후 자동 삭제)
2. `config_예시.txt`를 복사해 `config.txt`로 이름 변경 → 키·토큰·계정 ID 입력
3. 테스트: 폴더 주소창에 `cmd` → `pip install -r requirements.txt` → `python run_local.py --dry-run`
4. 실제 게시: `python run_local.py`
5. 매일 자동: `python schedule_setup.py 08:30` (윈도우 작업 스케줄러 등록, **PC가 켜져 있어야 실행**)
6. 결과 기록: `run_log.txt`

## 1. 인스타그램 계정 준비
1. 새 인스타 계정 생성 → 설정 → **계정 유형 → 프로페셔널 계정(크리에이터 또는 비즈니스)** 으로 전환
   (개인 계정은 API 게시 불가)

## 2. Meta 개발자 앱 + 토큰 발급 (2026년 '통합 로그인' 방식)
1. developers.facebook.com → 내 앱 → 앱 만들기 (이름에 Instagram/Facebook/Meta 금지, 예: `news_bot`)
2. 비즈니스 포트폴리오 만들기·연결 (무료, 인증 불필요)
3. 이용 사례 추가 → **Instagram에서 메시지 및 콘텐츠 관리**
4. 이용 사례 → 맞춤 설정 → **API setup with Unified login** → **새로운 구성 만들기**
   - 토큰: 시스템 사용자 액세스 토큰(만료 없음)
   - 자산: 인스타 계정 `@bosu_morning`, `@jinbo_morning`
   - 권한: `instagram_basic`, `instagram_content_publish` (나머지는 선택)
5. 계정별로 발급된 토큰을 각각 복사 (만료 없음, 갱신 불필요)
6. 인스타 계정 ID 확인: PC에서 `set IG_ACCESS_TOKEN=토큰` 후 `python find_ig_ids.py`
   (안 되면 비즈니스 설정 → 계정 → Instagram 계정에서 계정을 누르면 ID 표시)

## 3. GitHub 저장소
1. GitHub에서 **Public** 저장소 생성 (인스타가 이미지를 공개 URL로 가져가야 해서 공개여야 함)
2. 이 폴더 전체 업로드 (`.github` 폴더 포함)
3. Settings → Secrets and variables → Actions
   - **Secrets**
     - `ANTHROPIC_API_KEY` — https://console.anthropic.com 에서 발급
     - `IG_ACCESS_TOKEN_RIGHT` — @bosu_morning 토큰
     - `IG_ACCESS_TOKEN_LEFT` — @jinbo_morning 토큰
     - `IG_USER_ID_RIGHT` — @bosu_morning 계정 ID(숫자)
     - `IG_USER_ID_LEFT` — @jinbo_morning 계정 ID(숫자)
     (토큰이 `IG`로 시작하면 ID 없이도 게시되지만, 넣어 두면 확실합니다)
     - `FLICKR_API_KEY` — (선택) 정부 현장 사진용

## 4. 테스트 → 운영
1. Actions 탭 → **daily-politics-post** → Run workflow → `dry_run = true`, `channel = all`
   → 저장소 `posts/right/날짜/`, `posts/left/날짜/` 폴더의 카드와 `caption.txt` 확인
2. 마음에 들면 `dry_run = false`로 한 번 실행 → 인스타 게시 확인
3. 이후 매일 자동 실행

## 바꾸고 싶을 때
| 항목 | 위치 |
|---|---|
| 게시 시간 | `.github/workflows/daily.yml` 의 `cron` (UTC 기준, KST −9시간) |
| 이슈 개수 | 환경변수 `STORY_COUNT` (최대 8 — 캐러셀 10장 제한) |
| 뉴스 매체 | `bot/news.py` 의 `FEEDS` |
| 채널 시각·계정명·색·매체 | `channels/*.json` |
| 공통 금지 규칙 | `bot/summarize.py` 의 `RULES` |
| 색·폰트·레이아웃 | `bot/render.py` 상단 색상값 |

## 배경 사진 (모든 카드에 들어감)
우선순위: **① 그날 정부 공식 현장 사진 → ② 이슈 중심 인물 사진 → ③ 분야별 장소 사진 → ④ 기본 배경(광화문)**

### ① 그날 현장 사진 (정부 공식 Flickr)
- 코리아넷(대한민국 정부 공식 Flickr)에 매일 올라오는 대통령 일정·국무회의·정상회담·정부 행사 사진을 최근 3일 안에서 검색해 씁니다(CC BY-SA 2.0).
- AI가 정부 행사 관련 이슈에만 검색어를 붙입니다. 국회·정당 싸움 같은 이슈는 정부 사진이 없어서 ②~④로 넘어갑니다.
- **설정:** https://www.flickr.com/services/apps/create/apply/ 에서 비상업용(Non-Commercial) 키 발급 → GitHub Secret `FLICKR_API_KEY`로 등록. 키가 없으면 이 단계는 건너뜁니다.
- 언론사·통신사(연합뉴스, 뉴스1 등) 기사 사진은 저작권 침해라 쓰지 않습니다.

### ②~④
- `backgrounds/`에 국회·청와대 일대·대법원·정부청사·전쟁기념관·여의도·아파트·세종청사·서울시청·광화문 사진 **30장을 검수해서 넣어 뒀습니다**(전부 위키미디어 자유 라이선스, 저작자·라이선스는 `backgrounds/manifest.json`).
- 분야는 AI가 붙인 태그(국회, 대통령실, 사법, 외교, 안보, 경제, 부동산, 예산, 지방…)로 정해지고, 같은 분야라도 날짜별로 다른 사진을 씁니다.
- 사진을 추가하려면 `backgrounds/`에 파일을 넣고 manifest.json에 `{"file": "...", "credit": "사진: 저작자 / 라이선스"}`를 추가하세요.
- **그날 현장 사진(기사 사진)은 넣지 않습니다.** 언론사·통신사 사진은 저작권 침해입니다.

## 이미 만든 카드에 인물 사진 넣어 다시 만들기
`python rerender.py --channel left --date 2026-11-10` → `posts/left/2026-11-10/content.json`을 읽어 인물 사진을 넣어 다시 그립니다.
윈도우에서는 `오늘카드_사진넣기.bat` 더블클릭(파이썬 3.10+ 필요).

## 정치인 사진
- AI가 이슈마다 **중심 인물**을 고르면 봇이 위키데이터에 등록된 그 인물의 대표 사진을 **위키미디어 공용**에서 가져옵니다.
- 출처만 밝히면 상업적 이용·크롭이 가능한 라이선스(CC0, CC BY, CC BY-SA, 퍼블릭 도메인, 공공누리 1유형)만 받고, 카드 오른쪽 위에 **저작자 / 라이선스**를 자동 표기합니다.
- 사진이 없는 인물은 글자만 있는 카드로 나갑니다. 한 번 검색한 인물은 `photos/manifest.json`에 기록돼 다시 검색하지 않습니다.
- 직접 사진을 넣고 싶으면 `photos/홍길동.jpg`를 올리고 `manifest.json`에 `"홍길동": {"file": "홍길동.jpg", "credit": "사진: 출처 / 라이선스"}`를 추가하세요.
- ⚠️ **언론사·통신사 사진(연합뉴스, 뉴스1 등)은 절대 넣지 마세요.** 저작권 침해로 손해배상을 청구당할 수 있습니다. 정책브리핑(korea.kr) 사진도 대부분 연합뉴스 등에 저작권이 있어 별도 협의가 필요합니다.
- 인물 사진을 우스꽝스럽게 합성하거나 변형하면 초상권·명예훼손 문제가 생길 수 있어 크롭만 합니다.
- 자동 검색을 끄려면 환경변수 `AUTO_PHOTO=0`
- 정부 공식 Flickr(코리아넷) 출처 사진(CC BY-SA 2.0)도 포함합니다. 원본 안내문이 '언론 보도·공익 목적 이용'이므로 뉴스 게시물 용도로만 쓰고 광고·굿즈에는 쓰지 마세요.

## 주의
- 한 사람이 정반대 성향 계정 둘을 운영한다는 걸 숨기고 여론 조작처럼 보이게 쓰면 Meta의 '진정성 없는 행동' 정책에 걸릴 수 있습니다. 두 계정이 서로 맞팔·댓글로 싸움을 연출하는 식의 운영은 피하세요.
- 자동 게시라 사람 검수가 없습니다. 프롬프트에 "기사에 없는 사실 금지, 의혹은 의혹으로 표기, 비하 표현 금지" 규칙을 넣어 두었지만, 처음 1~2주는 dry_run으로 결과를 보고 톤을 조정하는 걸 권합니다.
- 한국은 사실 적시 명예훼손도 처벌 대상입니다. 개인 실명 + 의혹 기사는 특히 주의하세요.
- 언론사 기사 사진은 저작권 때문에 쓰지 않고 텍스트 카드만 만듭니다.
