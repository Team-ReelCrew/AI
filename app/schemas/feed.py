from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, NonNegativeInt

from app.schemas.card_news import Identifier, NonEmptyText

# trend: 주제 후보를 찾는 뉴스 피드, research: 원고 근거로 쓰는 공식 자료 피드
FeedRole = Literal["trend", "research"]


class _FeedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class FeedArticle(_FeedModel):
    article_id: Identifier
    feed_id: Identifier
    role: FeedRole
    publisher: NonEmptyText
    title: NonEmptyText
    url: HttpUrl
    published_at: AwareDatetime
    summary: str = ""


class FeedFailure(_FeedModel):
    feed_id: Identifier
    message: NonEmptyText


class FeedCollection(_FeedModel):
    collected_at: AwareDatetime
    articles: tuple[FeedArticle, ...]
    failures: tuple[FeedFailure, ...] = ()
    duplicate_count: NonNegativeInt = 0
    skipped_count: Annotated[
        NonNegativeInt, Field(description="제목·링크·발행 시각이 없어 제외한 항목 수")
    ] = 0
