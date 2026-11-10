"""Instagram API 캐러셀 게시.

기본: Meta '통합 로그인' 시스템 사용자 토큰(만료 없음) → graph.facebook.com + 인스타 계정 ID 필요
예전 Instagram 로그인 토큰을 쓰면 IG_API_HOST=graph.instagram.com, IG_USER_ID=me
"""
import os
import time

import requests

def _token():
    return os.environ["IG_ACCESS_TOKEN"].strip()


def _host() -> str:
    """토큰 종류로 게시 주소 자동 선택: IG... = 인스타 로그인 토큰, EAA... = 페이스북/시스템 사용자 토큰."""
    if os.getenv("IG_API_HOST"):
        return os.environ["IG_API_HOST"]
    return "graph.instagram.com" if _token().startswith("IG") else "graph.facebook.com"


API = f"https://{_host() if os.getenv('IG_ACCESS_TOKEN') else 'graph.facebook.com'}/{os.getenv('IG_API_VERSION', 'v25.0')}"


def _post(path, **data):
    data["access_token"] = _token()
    r = requests.post(f"{API}/{path}", data=data, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"POST {path} 실패 {r.status_code}: {r.text}")
    return r.json()


def _get(path, **params):
    params["access_token"] = _token()
    r = requests.get(f"{API}/{path}", params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def _wait_ready(container_id, tries=30):
    for _ in range(tries):
        st = _get(container_id, fields="status_code").get("status_code")
        if st == "FINISHED":
            return
        if st in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"컨테이너 {container_id} 상태: {st}")
        time.sleep(5)
    raise TimeoutError(f"컨테이너 {container_id} 준비 시간 초과")


def wait_url(url, tries=12):
    """GitHub raw URL이 실제로 열릴 때까지 대기."""
    for _ in range(tries):
        try:
            if requests.head(url, timeout=15).status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(10)
    raise TimeoutError(f"이미지 URL 접근 불가: {url}")


def publish_carousel(image_urls: list[str], caption: str) -> str:
    user = os.getenv("IG_USER_ID") or "me"
    if user == "me" and "graph.facebook.com" in API:
        raise SystemExit("IG_USER_ID(인스타 계정 ID)가 필요합니다 — find_ig_ids.py 로 확인하세요")
    for u in image_urls:
        wait_url(u)
    children = []
    for u in image_urls[:10]:  # 캐러셀 최대 10장
        cid = _post(f"{user}/media", image_url=u, is_carousel_item="true")["id"]
        children.append(cid)
    for cid in children:
        _wait_ready(cid)
    carousel = _post(f"{user}/media", media_type="CAROUSEL",
                     children=",".join(children), caption=caption)["id"]
    _wait_ready(carousel)
    media_id = _post(f"{user}/media_publish", creation_id=carousel)["id"]
    print(f"[publish] 게시 완료 media_id={media_id}")
    return media_id


def refresh_token() -> str:
    """장기 토큰(60일) 갱신. 발급 후 24시간 이후부터 가능."""
    r = requests.get("https://graph.instagram.com/refresh_access_token",
                     params={"grant_type": "ig_refresh_token", "access_token": _token()},
                     timeout=60)
    r.raise_for_status()
    return r.json()["access_token"]


def _wait_video(container_id, minutes=10):
    """릴스는 인스타 쪽 영상 처리에 몇 분 걸림."""
    for _ in range(minutes * 4):
        st = _get(container_id, fields="status_code,status").get("status_code")
        if st in ("FINISHED", "PUBLISHED"):
            return
        if st in ("ERROR", "EXPIRED"):
            info = _get(container_id, fields="status")
            raise RuntimeError(f"릴스 처리 실패: {info}")
        time.sleep(15)
    raise TimeoutError("릴스 처리 시간 초과")


def publish_reel(video_path: str, caption: str, public_url: str | None = None) -> str:
    """① 파일 직접 업로드(resumable) → 실패 시 ② public_url(video_url) 방식."""
    user = os.getenv("IG_USER_ID") or "me"
    version = os.getenv("IG_API_VERSION", "v25.0")
    if not public_url:
        cid = _post(f"{user}/media", media_type="REELS", upload_type="resumable",
                    caption=caption, share_to_feed="true")["id"]
        size = os.path.getsize(video_path)
        with open(video_path, "rb") as f:
            r = requests.post(f"https://rupload.facebook.com/ig-api-upload/{version}/{cid}",
                              headers={"Authorization": f"OAuth {_token()}", "offset": "0",
                                       "file_size": str(size)},
                              data=f, timeout=600)
        if r.status_code != 200 or not r.json().get("success"):
            raise RuntimeError(f"릴스 업로드 실패 {r.status_code}: {r.text[:300]}")
    else:
        cid = _post(f"{user}/media", media_type="REELS", video_url=public_url,
                    caption=caption, share_to_feed="true")["id"]
    _wait_video(cid)
    media_id = _post(f"{user}/media_publish", creation_id=cid)["id"]
    print(f"[publish] 릴스 게시 완료 media_id={media_id}")
    return media_id
