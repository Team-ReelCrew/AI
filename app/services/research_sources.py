from zoneinfo import ZoneInfo

from app.schemas.card_news import ResearchSource
from app.schemas.feed import FeedArticle

KST = ZoneInfo("Asia/Seoul")


class InsufficientSourceError(ValueError):
    def __init__(self, article_id: str, reason: str) -> None:
        self.article_id = article_id
        self.reason = reason
        super().__init__(f"{article_id}: {reason}")


def to_research_source(article: FeedArticle) -> ResearchSource:
    """공식 자료 피드의 기사를 원고 근거(ResearchSource)로 바꾼다.

    뉴스 피드(trend)의 요약은 주제 탐색에만 쓰고 원고 근거로 쓰지 않는다.
    """
    if article.role != "research":
        raise InsufficientSourceError(article.article_id, "원고 근거용 피드가 아닙니다.")
    if not article.summary:
        raise InsufficientSourceError(article.article_id, "요약 본문이 비어 있습니다.")

    return ResearchSource(
        source_id=article.article_id,
        title=article.title,
        publisher=article.publisher,
        url=article.url,
        published_on=article.published_at.astimezone(KST).date(),
        excerpt=article.summary,
    )
