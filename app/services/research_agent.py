from collections.abc import Sequence

from app.schemas.card_news import ResearchSource
from app.schemas.feed import FeedArticle
from app.schemas.topic import CandidateRejection, TopicCandidate, TopicResearch
from app.services.research_sources import InsufficientSourceError, to_research_source

MAX_SOURCES = 3
TITLE_WEIGHT = 2


def _compact(text: str) -> str:
    # "가계 대출"과 "가계대출"을 같게 본다.
    return "".join(text.split()).casefold()


def _score(keywords: Sequence[str], article: FeedArticle) -> int:
    title = _compact(article.title)
    summary = _compact(article.summary)
    score = 0
    for keyword in map(_compact, keywords):
        if keyword in title:
            score += TITLE_WEIGHT
        elif keyword in summary:
            score += 1
    return score


def find_sources(
    candidate: TopicCandidate, research_articles: Sequence[FeedArticle]
) -> list[ResearchSource]:
    """주제 키워드가 들어 있는 공식 자료를 점수순으로 고른다. LLM을 쓰지 않는다."""
    scored = [
        (score, article)
        for article in research_articles
        if (score := _score(candidate.keywords, article)) > 0
    ]
    scored.sort(key=lambda pair: (pair[0], pair[1].published_at), reverse=True)

    sources = []
    for _, article in scored:
        try:
            sources.append(to_research_source(article))
        except InsufficientSourceError:
            continue
        if len(sources) == MAX_SOURCES:
            break
    return sources


def research_candidates(
    candidates: Sequence[TopicCandidate], research_articles: Sequence[FeedArticle]
) -> tuple[TopicResearch | None, list[CandidateRejection]]:
    """순위대로 근거를 찾고, 근거가 있는 첫 후보를 고른다. 근거가 없으면 다음 후보로 넘어간다."""
    rejections = []
    for candidate in candidates:
        sources = find_sources(candidate, research_articles)
        if sources:
            return TopicResearch(candidate=candidate, sources=tuple(sources)), rejections
        rejections.append(
            CandidateRejection(
                candidate_id=candidate.candidate_id,
                reason=f"관련 공식 자료를 찾지 못했습니다. 키워드: {', '.join(candidate.keywords)}",
            )
        )
    return None, rejections
