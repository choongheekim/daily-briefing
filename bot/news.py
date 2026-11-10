"""정치 뉴스 RSS 수집."""
import html
import re
import time
from datetime import datetime, timedelta, timezone

import feedparser

KST = timezone(timedelta(hours=9))

# 보수·진보·통신사를 섞어 두면 여러 매체가 함께 다루는 '진짜 큰 이슈'를 고르기 쉽다.
FEEDS = {
    "연합뉴스": "https://www.yna.co.kr/rss/politics.xml",
    "조선일보": "https://www.chosun.com/arc/outboundfeeds/rss/category/politics/?outputType=xml",
    "동아일보": "https://rss.donga.com/politics.xml",
    "한겨레": "https://www.hani.co.kr/rss/politics/",
    "경향신문": "https://www.khan.co.kr/rss/rssdata/politic_news.xml",
    "중앙일보": "https://news.google.com/rss/search?q=site:joongang.co.kr+%EC%A0%95%EC%B9%98+when:1d&hl=ko&gl=KR&ceid=KR:ko",
    "매일경제": "https://www.mk.co.kr/rss/30200030/",
    "오마이뉴스": "https://rss.ohmynews.com/rss/politics.xml",
}


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_articles(sources: list[str] | None = None, hours: int = 24, per_feed: int = 40) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    articles = []
    for source, url in FEEDS.items():
        if sources and source not in sources:
            continue
        try:
            feed = feedparser.parse(url)
        except Exception as e:  # 한 곳이 죽어도 나머지로 진행
            print(f"[news] {source} 실패: {e}")
            continue
        count = 0
        for e in feed.entries:
            if count >= per_feed:
                break
            published = e.get("published_parsed") or e.get("updated_parsed")
            if published:
                dt = datetime.fromtimestamp(time.mktime(published), tz=timezone.utc)
                if dt < cutoff:
                    continue
            title = _clean(e.get("title", ""))
            title = re.sub(r"\s+-\s+[^-]+$", "", title) if "news.google" in url else title
            if not title:
                continue
            articles.append({
                "source": source,
                "title": title,
                "summary": _clean(e.get("summary", ""))[:400],
                "link": e.get("link", ""),
            })
            count += 1
        print(f"[news] {source}: {count}건")
    return articles
