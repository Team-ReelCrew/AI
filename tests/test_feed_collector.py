import asyncio
from datetime import UTC, date, datetime

import httpx
import pytest

from app.schemas.feed import FeedArticle
from app.services.feed_collector import (
    USER_AGENT,
    Feed,
    clean_summary,
    collect_articles,
    normalize_url,
)
from app.services.research_sources import InsufficientSourceError, to_research_source

NEWS_FEED = Feed("news-a", "가상경제", "https://news-a.test/rss", "trend")
OTHER_NEWS_FEED = Feed("news-b", "나상경제", "https://news-b.test/rss", "trend")
OFFICIAL_FEED = Feed("official", "가상은행", "https://official.test/rss", "research")


def rss(*items: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
        f"<title>테스트</title>{''.join(items)}</channel></rss>"
    )


def item(title: str, link: str, published: str | None, summary: str = "") -> str:
    published_tag = f"<pubDate>{published}</pubDate>" if published else ""
    return (
        f"<item><title><![CDATA[{title}]]></title><link><![CDATA[{link}]]></link>"
        f"{published_tag}<description><![CDATA[{summary}]]></description></item>"
    )


NEWS_A = rss(
    item("기준금리 동결", "https://news-a.test/1?utm_source=rss#top", "Wed, 25 Nov 2026 10:00:00 +0900", "요약 A"),
    item("오래된 기사", "https://news-a.test/old", "Mon, 23 Nov 2026 10:00:00 +0900"),
    item("날짜 없는 기사", "https://news-a.test/nodate", None),
)
NEWS_B = rss(
    item("기준금리 동결 (다른 피드)", "https://NEWS-A.test/1/", "Wed, 25 Nov 2026 11:00:00 +0900"),
    item("환율 상승", "https://news-b.test/2", "Wed, 25 Nov 2026 12:00:00 +0900"),
)
# 한국은행 RSS처럼 HTML을 한 번 더 이스케이프한 요약
OFFICIAL = rss(
    item(
        "10월 금리 동향",
        "https://official.test/view.do?nttId=7&menuNo=1",
        "Wed, 25 Nov 2026 12:00:00 +0900",
        "&lt;p style=&quot;x&quot;&gt;&lt;span&gt;□ 대출금리는 연 4.64%&amp;nbsp;상승&lt;br&gt;&lt;/span&gt;&lt;/p&gt;"
        "&lt;p&gt;&amp;nbsp; ― 자세한 내용은 &amp;lt;붙임&amp;gt; 참조&lt;/p&gt;",
    ),
)
RESPONSES = {
    "news-a.test": NEWS_A,
    "news-b.test": NEWS_B,
    "official.test": OFFICIAL,
}


def run_collect(feeds: tuple[Feed, ...], **kwargs: object) -> tuple:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = RESPONSES.get(request.url.host)
        if body is None:
            return httpx.Response(500)
        return httpx.Response(200, text=body)

    async def collect():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), headers={"User-Agent": USER_AGENT}
        ) as client:
            return await collect_articles(feeds, client=client, **kwargs)

    return asyncio.run(collect()), requests


def test_normalize_url_removes_tracking_and_keeps_meaningful_query() -> None:
    assert (
        normalize_url("HTTPS://Example.com/view.do/?utm_source=rss&nttId=7&menuNo=1#top")
        == "https://example.com/view.do?menuNo=1&nttId=7"
    )


def test_collect_removes_duplicates_across_feeds_and_sorts_latest_first() -> None:
    collection, requests = run_collect((NEWS_FEED, OTHER_NEWS_FEED))

    assert [article.title for article in collection.articles] == [
        "환율 상승",
        "기준금리 동결",
        "오래된 기사",
    ]
    assert collection.duplicate_count == 1
    assert collection.skipped_count == 1
    assert collection.failures == ()
    assert all(request.headers["User-Agent"] == USER_AGENT for request in requests)


def test_collect_filters_by_since() -> None:
    since = datetime(2026, 11, 24, tzinfo=UTC)
    collection, _ = run_collect((NEWS_FEED,), since=since)

    assert [article.title for article in collection.articles] == ["기준금리 동결"]


def test_failed_feed_is_reported_without_dropping_others() -> None:
    broken = Feed("broken", "고장", "https://broken.test/rss", "trend")
    collection, _ = run_collect((broken, NEWS_FEED))

    assert [failure.feed_id for failure in collection.failures] == ["broken"]
    assert "500" in collection.failures[0].message
    assert len(collection.articles) == 2


def test_double_escaped_html_summary_becomes_plain_lines() -> None:
    collection, _ = run_collect((OFFICIAL_FEED,))

    assert collection.articles[0].summary == (
        "□ 대출금리는 연 4.64% 상승\n― 자세한 내용은 <붙임> 참조"
    )


def test_clean_summary_keeps_plain_text() -> None:
    assert clean_summary("  고객 8만6000여명   정보 유출 & 대응 ") == "고객 8만6000여명 정보 유출 & 대응"


def test_research_source_uses_korean_date_and_summary() -> None:
    collection, _ = run_collect((OFFICIAL_FEED,))
    article = collection.articles[0].model_copy(
        update={"published_at": datetime(2026, 11, 24, 16, 0, tzinfo=UTC)}
    )

    source = to_research_source(article)

    assert source.published_on == date(2026, 11, 25)
    assert source.source_id == article.article_id
    assert source.excerpt.startswith("□ 대출금리는")


@pytest.mark.parametrize(
    ("role", "summary"),
    [("trend", "요약 있음"), ("research", "")],
)
def test_research_source_rejects_news_or_empty_summary(role: str, summary: str) -> None:
    article = FeedArticle(
        article_id="a-1",
        feed_id="a",
        role=role,
        publisher="가상",
        title="제목",
        url="https://a.test/1",
        published_at=datetime(2026, 11, 25, tzinfo=UTC),
        summary=summary,
    )

    with pytest.raises(InsufficientSourceError):
        to_research_source(article)
