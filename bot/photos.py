"""인물 사진 확보: ① photos/ 폴더에 직접 넣은 사진 → ② 위키데이터 대표사진(위키미디어 공용).

언론사 사진은 저작권 문제로 절대 쓰지 않는다.
위키미디어 공용은 자유 라이선스 사진만 올라오지만, 라이선스를 한 번 더 확인하고
저작자·라이선스를 manifest.json 에 기록해 카드에 표시한다.

manifest.json 형식 (직접 추가할 때도 같은 형식)
{
  "홍길동": {"file": "홍길동.jpg", "credit": "사진: 국회 / 공공누리 제1유형"}
}
"""
import html
import json
import os
import re

import requests

DIR = "photos"
MANIFEST = os.path.join(DIR, "manifest.json")
import time

# 위키미디어 정책: User-Agent에 연락 가능한 URL 포함 필요
_REPO = os.getenv("GITHUB_REPOSITORY", "unknown/insta-news-bot")
UA = {"User-Agent": f"insta-news-bot/1.0 (https://github.com/{_REPO}) python-requests"}


def _api(url, params, tries=5):
    """429·5xx면 대기 후 재시도."""
    params = {**params, "format": "json", "maxlag": 5}
    for i in range(tries):
        r = requests.get(url, headers=UA, params=params, timeout=30)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("application/json"):
            data = r.json()
            if data.get("error", {}).get("code") != "maxlag":
                return data
        wait = int(r.headers.get("Retry-After", 0) or 0) or 5 * (2 ** i)
        print(f"[photos] {r.status_code} → {wait}초 후 재시도")
        time.sleep(min(wait, 60))
    raise RuntimeError(f"위키미디어 API 응답 실패: {r.status_code}")

# 출처표시만 하면 상업적 이용·변형(크롭) 가능한 라이선스만 허용
ALLOWED = re.compile(r"^(CC0|CC BY(-SA)? [0-9.]+|Public domain|PD|KOGL Type 1|공공누리 제?1유형)", re.I)
# 카드에 쓰기 전 출처 문구에 '확인된 라이선스'가 있는지 검사(없으면 그 사진은 안 씀)
LICENSE_IN_CREDIT = re.compile(r"(CC0|CC BY(-SA)? ?[0-9.]*|Public domain|KOGL Type 1|공공누리 ?제?1유형|Pexels)", re.I)


def license_ok(credit: str | None) -> bool:
    return bool(credit) and bool(LICENSE_IN_CREDIT.search(credit))
POLITICAL = ("정치인", "국회의원", "대통령", "장관", "총리", "시장", "도지사", "법조인",
             "관료", "외교관", "검사", "판사", "군인", "정당인", "의원")
POLITICIAN_QID = "Q82955"


def clean_artist(artist: str) -> str:
    a = re.sub(r"\s+", " ", artist).strip(" ,")
    if re.search(r"Republic of\s+Korea|Korea\.net|코리아넷", a, re.I):
        return "Korea.net(대한민국 정부)"
    if "국군" in a:
        return "대한민국 국군"
    return a[:30] or "작자 미상"


def _load() -> dict:
    if os.path.exists(MANIFEST):
        with open(MANIFEST, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save(m: dict):
    os.makedirs(DIR, exist_ok=True)
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)


def _wikidata_image(name: str) -> str | None:
    """한국어 이름으로 정치 관련 인물을 찾아 P18(대표 이미지) 파일명 반환."""
    res = _api("https://www.wikidata.org/w/api.php", {
        "action": "wbsearchentities", "search": name, "language": "ko",
        "uselang": "ko", "type": "item", "limit": 5})
    ids = [e["id"] for e in res.get("search", [])
           if name in (e.get("label"), e.get("match", {}).get("text"))]
    if not ids:
        return None
    ents = _api("https://www.wikidata.org/w/api.php", {
        "action": "wbgetentities", "ids": "|".join(ids), "props": "claims|descriptions",
        "languages": "ko"})["entities"]
    for qid in ids:  # 동명이인 대비: 정치 관련 인물만
        ent = ents[qid]
        claims = ent.get("claims", {})
        desc = ent.get("descriptions", {}).get("ko", {}).get("value", "")
        jobs = {c["mainsnak"].get("datavalue", {}).get("value", {}).get("id")
                for c in claims.get("P106", [])}
        if POLITICIAN_QID not in jobs and not any(k in desc for k in POLITICAL):
            continue
        if "P18" in claims:
            return claims["P18"][0]["mainsnak"]["datavalue"]["value"]
    return None


def _img_url(info: dict) -> str:
    """위키미디어는 표준 크기(…960/1280/1920/3840px)만 허용(그 외는 429 차단).
    원본이 1920px 이하면 원본, 크면 1920px 표준 썸네일."""
    if info.get("width", 0) <= 1920 or not info.get("thumburl"):
        return info["url"]
    return info["thumburl"].split("?")[0]


def _commons_fetch(filename: str, dest: str) -> str | None:
    res = _api("https://commons.wikimedia.org/w/api.php", {
        "action": "query", "titles": f"File:{filename}", "prop": "imageinfo",
        "iiprop": "url|extmetadata|size", "iiurlwidth": 1920})
    page = next(iter(res["query"]["pages"].values()))
    info = page["imageinfo"][0]
    meta = info.get("extmetadata", {})
    lic = meta.get("LicenseShortName", {}).get("value", "")
    if not ALLOWED.match(lic):
        print(f"[photos] 라이선스 제외: {filename} ({lic})")
        return None
    artist = re.sub(r"<[^>]+>", "", html.unescape(meta.get("Artist", {}).get("value", ""))).strip()
    img = requests.get(_img_url(info), headers=UA, timeout=60)
    img.raise_for_status()
    with open(dest, "wb") as f:
        f.write(img.content)
    return f"사진: {clean_artist(artist)} / {lic} / Wikimedia Commons"


def get_photo(name: str | None) -> tuple[str, str] | None:
    """(파일경로, 출처표시) 또는 None."""
    if not name:
        return None
    m = _load()
    if name in m:
        e = m[name]
        p = os.path.join(DIR, e["file"])
        stale = e["file"] and not e.get("manual") and not e.get("source")   # 예전 저화질(1200px) 자동 사진
        if not stale or os.getenv("AUTO_PHOTO", "1") != "1":
            if os.path.exists(p) and e["file"] and license_ok(e["credit"]):
                return p, e["credit"]
            if e["file"] and not license_ok(e["credit"]):
                print(f"[photos] {name}: 출처에 라이선스가 없어 사용 안 함 → manifest.json에 라이선스 적어 주세요")
            return None
    if os.getenv("AUTO_PHOTO", "1") != "1":
        return None
    try:
        fn = _wikidata_image(name)
        credit = None
        if fn:
            os.makedirs(DIR, exist_ok=True)
            ext = os.path.splitext(fn)[1].lower() or ".jpg"
            local = f"{name}{ext}"
            credit = _commons_fetch(fn, os.path.join(DIR, local))
        # 못 찾은 사람도 기록(매일 재검색 방지). 나중에 직접 사진 넣으면 덮어쓰면 됨
        if not credit and name in m and m[name].get("file"):   # 고화질 재시도 실패 → 기존 사진 유지
            old = m[name]
            m[name] = {**old, "source": old.get("source") or "unknown"}
            _save(m)
            return (os.path.join(DIR, old["file"]), old["credit"]) if license_ok(old["credit"]) else None
        m[name] = {"file": local if credit else "", "credit": credit or "", "source": fn or ""}
        _save(m)
        print(f"[photos] {name}: {'확보' if credit else '없음'}")
        time.sleep(1)  # 연속 호출 간격
        return (os.path.join(DIR, local), credit) if credit else None
    except Exception as e:
        print(f"[photos] {name} 검색 실패: {e}")
        old = m.get(name) or {}
        p = os.path.join(DIR, old.get("file") or "_")
        return (p, old["credit"]) if old.get("file") and os.path.exists(p) and license_ok(old["credit"]) else None
