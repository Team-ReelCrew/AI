from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.schemas.card_news import Identifier, NonEmptyText, ResearchSource
from app.schemas.llm import LLMCallRecord


# LLM 구조화 출력용 모델. 제약은 코드에서 검사하므로 단순한 타입만 둔다.
class TopicClusterDraft(BaseModel):
    topic: str = Field(description="카드뉴스 주제를 한 줄로 요약")
    article_ids: list[str] = Field(description="이 주제를 다룬 기사 ID")
    reason: str = Field(description="카드뉴스 주제로 적합한 이유 한 문장")
    keywords: list[str] = Field(description="공식 경제 자료에서 찾을 경제 용어 2~5개")


class TopicClusteringOutput(BaseModel):
    clusters: list[TopicClusterDraft]


class _TopicModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class TopicCandidate(_TopicModel):
    candidate_id: Identifier
    topic: NonEmptyText
    article_ids: Annotated[tuple[Identifier, ...], Field(min_length=1)]
    publishers: Annotated[tuple[NonEmptyText, ...], Field(min_length=1)]
    reason: NonEmptyText
    keywords: Annotated[tuple[NonEmptyText, ...], Field(min_length=1)]
    latest_published_at: AwareDatetime


class TopicResearch(_TopicModel):
    candidate: TopicCandidate
    sources: Annotated[tuple[ResearchSource, ...], Field(min_length=1)]


class CandidateRejection(_TopicModel):
    candidate_id: Identifier
    reason: NonEmptyText


class DiscoveryFailure(_TopicModel):
    stage: Literal["trend", "research"]
    code: NonEmptyText
    message: NonEmptyText


class TopicDiscoveryResult(_TopicModel):
    candidates: tuple[TopicCandidate, ...] = ()
    selected: TopicResearch | None = None
    rejections: tuple[CandidateRejection, ...] = ()
    failure: DiscoveryFailure | None = None
    llm_calls: tuple[LLMCallRecord, ...] = ()
