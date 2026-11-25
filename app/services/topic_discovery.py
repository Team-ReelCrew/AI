import argparse
import asyncio
from datetime import UTC, datetime, timedelta

from dotenv import load_dotenv
from openai import OpenAIError

from app.schemas.feed import FeedCollection
from app.schemas.topic import DiscoveryFailure, TopicDiscoveryResult
from app.services.feed_collector import collect_articles
from app.services.llm import LLMConfigError, LLMOutputError, StructuredLLM
from app.services.research_agent import research_candidates
from app.services.trend_agent import find_topic_candidates

TREND_WINDOW = timedelta(hours=24)
# 공식 보도자료는 뉴스보다 드물어서 더 긴 기간에서 근거를 찾는다.
RESEARCH_WINDOW = timedelta(days=30)


async def discover_topic(
    collection: FeedCollection, llm: StructuredLLM, *, now: datetime | None = None
) -> TopicDiscoveryResult:
    """Trend로 주제 후보를 만들고 Research로 근거가 있는 첫 후보를 고른다."""
    now = now or datetime.now(UTC)
    trend_articles = [
        article
        for article in collection.articles
        if article.role == "trend" and article.published_at >= now - TREND_WINDOW
    ]
    research_articles = [
        article
        for article in collection.articles
        if article.role == "research" and article.published_at >= now - RESEARCH_WINDOW
    ]

    def failed(stage: str, code: str, message: str, **fields: object) -> TopicDiscoveryResult:
        return TopicDiscoveryResult(
            failure=DiscoveryFailure(stage=stage, code=code, message=message),
            llm_calls=tuple(llm.calls),
            **fields,
        )

    if not trend_articles:
        failed_feeds = ", ".join(failure.feed_id for failure in collection.failures)
        detail = f" 실패한 피드: {failed_feeds}" if failed_feeds else ""
        return failed("trend", "NO_TREND_ARTICLES", f"최근 뉴스 기사가 없습니다.{detail}")

    try:
        candidates = await find_topic_candidates(llm, trend_articles)
    except (LLMConfigError, LLMOutputError, OpenAIError) as error:
        return failed("trend", "LLM_CALL_FAILED", str(error) or type(error).__name__)
    if not candidates:
        return failed("trend", "NO_TOPIC_CANDIDATES", "주제 후보를 만들지 못했습니다.")

    selected, rejections = research_candidates(candidates, research_articles)
    if selected is None:
        return failed(
            "research",
            "INSUFFICIENT_SOURCES",
            "모든 주제 후보에서 근거 자료를 찾지 못했습니다.",
            candidates=tuple(candidates),
            rejections=tuple(rejections),
        )

    return TopicDiscoveryResult(
        candidates=tuple(candidates),
        selected=selected,
        rejections=tuple(rejections),
        llm_calls=tuple(llm.calls),
    )


async def run() -> TopicDiscoveryResult:
    collection = await collect_articles()
    return await discover_topic(collection, StructuredLLM())


def main() -> None:
    argparse.ArgumentParser(
        description="경제 RSS에서 주제 후보를 만들고 근거 자료가 있는 주제를 고릅니다."
    ).parse_args()
    load_dotenv()
    print(asyncio.run(run()).model_dump_json(indent=2))


if __name__ == "__main__":
    main()
