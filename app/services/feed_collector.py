import argparse
import asyncio
from calendar import timegm
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha1
from html import unescape
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import httpx
from pydantic import ValidationError

from app.schemas.feed import FeedArticle, FeedCollection, FeedFailure, FeedRole

# 일부 언론사는 기본 python-httpx User-Agent를 403으로 차단한다.
USER_AGENT = "ReelCrew/0.1 (+https://github.com/Team-ReelCrew/AI)"
REQUEST_TIMEOUT_SECONDS = 10.0
TRACKING_PARAM_PREFIXES = ("utm_",)
TRACKING_PARAMS = frozenset({"fbclid", "gclid", "igshid"})


@dataclass(frozen=True)
class Feed:
    feed_id: str
    publisher: str
    url: str
    role: FeedRole


# 연합뉴스 RSS는 저작권 표시에서 AI 학습·활용을 금지하므로 기본 피드에서 제외한다.
DEFAULT_FEEDS = (
    Feed("mk-economy", "매일경제", "https://www.mk.co.kr/rss/30100041/", "trend"),
    Feed("hankyung-economy", "한국경제", "https://www.hankyung.com/feed/economy", "trend"),
    Feed(
        "bok-press",
        "한국은행",
        "https://www.bok.or.kr/portal/bbs/B0000501/news.rss?menuNo=201264",
        "research",
    ),
)


class FeedFetchError(Exception):
    pass


def normalize_url(url: str) -> str:
    """중복 판별용 URL: 추적 파라미터와 fragment를 지우고 쿼리를 정렬한다."""
    parts = urlsplit(url.strip())
    query = sorted(
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMS
        and not key.lower().startswith(TRACKING_PARAM_PREFIXES)
    )
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), "")
    )


class _TextExtractor(HTMLParser):
    BLOCK_TAGS = frozenset({"p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def clean_summary(raw: str) -> str:
    """RSS 요약의 HTML을 줄 단위 텍스트로 바꾼다."""
    # 한국은행 RSS는 HTML을 한 번 더 이스케이프해서 보낸다.
    text = unescape(raw) if "&lt;" in raw else raw
    extractor = _TextExtractor()
    extractor.feed(text)
    extractor.close()
    lines = (" ".join(line.split()) for line in "".join(extractor.parts).splitlines())
    return "\n".join(line for line in lines if line)


def _article_id(feed_id: str, normalized_url: str) -> str:
    return f"{feed_id}-{sha1(normalized_url.encode()).hexdigest()[:12]}"


def parse_feed(feed: Feed, content: bytes) -> tuple[list[FeedArticle], int]:
    """피드 본문을 기사 목록과 제외한 항목 수로 바꾼다."""
    parsed = feedparser.parse(content)
    if parsed.bozo and not parsed.entries:
        raise FeedFetchError(f"RSS를 해석할 수 없습니다: {parsed.bozo_exception}")

    articles = []
    skipped = 0
    for entry in parsed.entries:
        link = entry.get("link")
        published = entry.get("published_parsed") or entry.get("updated_parsed")
        if not link or not published or not entry.get("title"):
            skipped += 1
            continue

        url = normalize_url(link)
        try:
            articles.append(
                FeedArticle(
                    article_id=_article_id(feed.feed_id, url),
                    feed_id=feed.feed_id,
                    role=feed.role,
                    publisher=feed.publisher,
                    title=clean_summary(entry.title).replace("\n", " "),
                    url=url,
                    published_at=datetime.fromtimestamp(timegm(published), UTC),
                    summary=clean_summary(entry.get("summary", "")),
                )
            )
        except ValidationError:
            skipped += 1
    return articles, skipped


async def fetch_feed(client: httpx.AsyncClient, feed: Feed) -> tuple[list[FeedArticle], int]:
    try:
        response = await client.get(feed.url)
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise FeedFetchError(f"{type(error).__name__}: {error}") from error
    return parse_feed(feed, response.content)


async def collect_articles(
    feeds: tuple[Feed, ...] = DEFAULT_FEEDS,
    *,
    since: datetime | None = None,
    client: httpx.AsyncClient | None = None,
) -> FeedCollection:
    """피드를 동시에 가져와 중복을 제거하고 최신순으로 반환한다.

    한 피드가 실패해도 나머지 피드의 기사는 반환하고, 실패는 failures에 남긴다.
    """
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=True,
        )

    try:
        results = await asyncio.gather(
            *(fetch_feed(client, feed) for feed in feeds), return_exceptions=True
        )
    finally:
        if owns_client:
            await client.aclose()

    articles: list[FeedArticle] = []
    failures: list[FeedFailure] = []
    seen_urls: set[str] = set()
    duplicate_count = 0
    skipped_count = 0
    for feed, result in zip(feeds, results, strict=True):
        if isinstance(result, FeedFetchError):
            failures.append(FeedFailure(feed_id=feed.feed_id, message=str(result)))
            continue
        if isinstance(result, BaseException):
            raise result

        feed_articles, skipped = result
        skipped_count += skipped
        for article in feed_articles:
            if since is not None and article.published_at < since:
                continue
            if str(article.url) in seen_urls:
                duplicate_count += 1
                continue
            seen_urls.add(str(article.url))
            articles.append(article)

    articles.sort(key=lambda article: article.published_at, reverse=True)
    return FeedCollection(
        collected_at=datetime.now(UTC),
        articles=tuple(articles),
        failures=tuple(failures),
        duplicate_count=duplicate_count,
        skipped_count=skipped_count,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="경제 RSS를 수집해 JSON으로 출력합니다.")
    parser.add_argument(
        "--hours", type=float, default=24, help="최근 몇 시간 안의 기사만 남길지 (기본 24)"
    )
    args = parser.parse_args()

    since = datetime.now(UTC) - timedelta(hours=args.hours)
    collection = asyncio.run(collect_articles(since=since))
    print(collection.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
