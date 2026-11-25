from datetime import date
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StrictInt, model_validator

from app.schemas.job import IDENTIFIER_PATTERN

CARD_COUNT = 5
Identifier = Annotated[str, Field(pattern=IDENTIFIER_PATTERN)]
NonEmptyText = Annotated[str, Field(min_length=1)]


class _CardNewsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ResearchSource(_CardNewsModel):
    source_id: Identifier
    title: NonEmptyText
    publisher: NonEmptyText
    url: HttpUrl
    published_on: date
    excerpt: NonEmptyText


class CardDraft(_CardNewsModel):
    card_id: Identifier
    order: StrictInt
    title: NonEmptyText
    body: NonEmptyText
    source_ids: Annotated[tuple[Identifier, ...], Field(min_length=1)]


class CardNewsDraft(_CardNewsModel):
    template_id: Literal["economy-brief-v1"]
    cards: Annotated[
        tuple[CardDraft, ...], Field(min_length=CARD_COUNT, max_length=CARD_COUNT)
    ]
    caption: NonEmptyText

    @model_validator(mode="after")
    def validate_cards(self) -> Self:
        if [card.order for card in self.cards] != list(range(1, CARD_COUNT + 1)):
            raise ValueError(f"카드 순서는 1부터 {CARD_COUNT}까지 연속되어야 합니다.")
        if len({card.card_id for card in self.cards}) != len(self.cards):
            raise ValueError("카드 ID는 중복될 수 없습니다.")
        return self


class CardNewsContent(_CardNewsModel):
    sources: Annotated[tuple[ResearchSource, ...], Field(min_length=1)]
    draft: CardNewsDraft

    @model_validator(mode="after")
    def validate_source_references(self) -> Self:
        source_ids = {source.source_id for source in self.sources}
        if len(source_ids) != len(self.sources):
            raise ValueError("출처 ID는 중복될 수 없습니다.")

        for card in self.draft.cards:
            unknown_ids = set(card.source_ids) - source_ids
            if unknown_ids:
                unknown = ", ".join(sorted(unknown_ids))
                raise ValueError(
                    f"카드 {card.card_id}에 등록되지 않은 출처 ID({unknown})가 있습니다."
                )
        return self
