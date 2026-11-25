import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.schemas.feed import FeedArticle, FeedCollection, FeedFailure
from app.schemas.topic import TopicClusterDraft, TopicClusteringOutput
from app.services.llm import LLMConfigError, LLMOutputError, StructuredLLM, model_for
from app.services.topic_discovery import discover_topic

NOW = datetime(2026, 11, 25, 12, tzinfo=UTC)


def article(
    article_id: str,
    title: str,
    *,
    role: str = "trend",
    publisher: str = "가상경제",
    summary: str = "",
    hours_ago: float = 1,
) -> FeedArticle:
    return FeedArticle(
        article_id=article_id,
        feed_id=f"{role}-feed",
        role=role,
        publisher=publisher,
        title=title,
        url=f"https://example.test/{article_id}",
        published_at=NOW - timedelta(hours=hours_ago),
        summary=summary,
    )


def response(
    parsed: BaseModel | None,
    *,
    status: str = "completed",
    refusal: str | None = None,
    incomplete_reason: str | None = None,
) -> SimpleNamespace:
    content = [SimpleNamespace(type="refusal", refusal=refusal)] if refusal else []
    return SimpleNamespace(
        model="test-model-2026",
        status=status,
        incomplete_details=SimpleNamespace(reason=incomplete_reason),
        output=[SimpleNamespace(type="message", content=content)],
        output_parsed=parsed,
        usage=SimpleNamespace(
            input_tokens=1200,
            output_tokens=300,
            input_tokens_details=SimpleNamespace(cached_tokens=200),
            output_tokens_details=SimpleNamespace(reasoning_tokens=50),
        ),
    )


class FakeResponses:
    def __init__(self, *responses: SimpleNamespace) -> None:
        self._responses = list(responses)
        self.requests: list[dict] = []

    async def parse(self, **request: object) -> SimpleNamespace:
        self.requests.append(request)
        return self._responses.pop(0)


def fake_llm(*responses: SimpleNamespace) -> tuple[StructuredLLM, FakeResponses]:
    fake = FakeResponses(*responses)
    return StructuredLLM(client=SimpleNamespace(responses=fake)), fake


def clusters(*drafts: tuple[str, list[str], list[str]]) -> TopicClusteringOutput:
    return TopicClusteringOutput(
        clusters=[
            TopicClusterDraft(topic=topic, article_ids=ids, reason=f"{topic} 이유", keywords=keywords)
            for topic, ids, keywords in drafts
        ]
    )


NEWS = (
    article("n1", "대출금리 또 올랐다", publisher="가상경제"),
    article("n2", "예금금리 상승세", publisher="나상경제"),
    article("n3", "반도체 수출 호조", publisher="가상경제", hours_ago=2),
    article("old", "어제 기사", hours_ago=30),
)
BOK = (
    article(
        "bok1",
        "2026년 10월 금융기관 가중평균금리",
        role="research",
        publisher="한국은행",
        summary="대출금리는 연 4.64%로 전월대비 0.07%p 상승",
        hours_ago=5,
    ),
    article("bok-empty", "대출금리 참고자료", role="research", publisher="한국은행", hours_ago=6),
    article(
        "bok-old",
        "작년 대출금리",
        role="research",
        publisher="한국은행",
        summary="오래된 자료",
        hours_ago=24 * 40,
    ),
)


@pytest.fixture(autouse=True)
def default_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REELCREW_DEFAULT_MODEL", "test-model")
    monkeypatch.delenv("REELCREW_TREND_MODEL", raising=False)


def run(collection: FeedCollection, llm: StructuredLLM):
    return asyncio.run(discover_topic(collection, llm, now=NOW))


def collection(*articles: FeedArticle, failures: tuple[FeedFailure, ...] = ()) -> FeedCollection:
    return FeedCollection(collected_at=NOW, articles=articles, failures=failures)


def test_selects_highest_ranked_candidate_with_official_source() -> None:
    llm, fake = fake_llm(
        response(
            clusters(
                ("반도체 수출", ["n3"], ["수출"]),
                ("금리 상승", ["n1", "n2", "없는-id"], ["대출금리", "예금 금리"]),
            )
        )
    )

    result = run(collection(*NEWS, *BOK), llm)

    assert result.failure is None
    assert [c.candidate_id for c in result.candidates] == ["topic-1", "topic-2"]
    top = result.candidates[0]
    assert top.topic == "금리 상승"  # 매체 2곳이 다뤄 1순위
    assert top.article_ids == ("n1", "n2")  # LLM이 만든 없는 ID는 버림
    assert top.publishers == ("가상경제", "나상경제")
    assert result.selected.candidate == top
    # 요약이 빈 자료와 30일보다 오래된 자료는 근거에서 빠진다.
    assert [s.source_id for s in result.selected.sources] == ["bok1"]
    # 24시간보다 오래된 기사는 LLM 입력에 넣지 않는다.
    prompt = fake.requests[0]["input"]
    assert "n1 | 가상경제 | 대출금리 또 올랐다" in prompt
    assert "old" not in prompt
    assert fake.requests[0]["text_format"] is TopicClusteringOutput


def test_moves_to_next_candidate_when_first_has_no_source() -> None:
    llm, _ = fake_llm(
        response(
            clusters(
                ("환율 급등", ["n1", "n2"], ["환율"]),
                ("금리 상승", ["n3"], ["가중평균금리"]),
            )
        )
    )

    result = run(collection(*NEWS, *BOK), llm)

    assert result.selected.candidate.topic == "금리 상승"
    assert [r.candidate_id for r in result.rejections] == ["topic-1"]
    assert "환율" in result.rejections[0].reason


def test_fails_when_no_candidate_has_sources() -> None:
    llm, _ = fake_llm(response(clusters(("환율 급등", ["n1"], ["환율"]))))

    result = run(collection(*NEWS, *BOK), llm)

    assert result.selected is None
    assert result.failure.stage == "research"
    assert result.failure.code == "INSUFFICIENT_SOURCES"
    assert len(result.rejections) == 1


def test_no_news_skips_llm_call() -> None:
    llm, fake = fake_llm()
    failure = FeedFailure(feed_id="mk-economy", message="403")

    result = run(collection(*BOK, failures=(failure,)), llm)

    assert result.failure.code == "NO_TREND_ARTICLES"
    assert "mk-economy" in result.failure.message
    assert fake.requests == []
    assert result.llm_calls == ()


def test_records_tokens_and_time_per_call() -> None:
    llm, _ = fake_llm(response(clusters(("금리 상승", ["n1"], ["대출금리"]))))

    result = run(collection(*NEWS, *BOK), llm)

    (call,) = result.llm_calls
    assert call.agent == "trend"
    assert call.requested_model == "test-model"
    assert call.served_model == "test-model-2026"
    assert (call.input_tokens, call.output_tokens) == (1200, 300)
    assert (call.cached_input_tokens, call.reasoning_tokens) == (200, 50)
    assert call.duration_seconds >= 0


@pytest.mark.parametrize(
    "bad_response",
    [
        response(None, refusal="거절"),
        response(None, status="incomplete", incomplete_reason="max_output_tokens"),
        response(None),
    ],
)
def test_llm_problems_become_trend_failure_but_are_logged(bad_response: SimpleNamespace) -> None:
    llm, _ = fake_llm(bad_response)

    result = run(collection(*NEWS, *BOK), llm)

    assert result.failure.stage == "trend"
    assert result.failure.code == "LLM_CALL_FAILED"
    assert len(result.llm_calls) == 1  # 실패한 호출도 토큰을 썼으므로 기록한다.


def test_parse_raises_output_error_on_refusal() -> None:
    llm, _ = fake_llm(response(None, refusal="거절"))

    with pytest.raises(LLMOutputError, match="거절"):
        asyncio.run(
            llm.parse(agent="trend", system="s", prompt="p", output_type=TopicClusteringOutput)
        )


def test_agent_model_overrides_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REELCREW_TREND_MODEL", "cheap-model")

    assert model_for("trend") == "cheap-model"
    assert model_for("script") == "test-model"


def test_missing_model_config_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REELCREW_DEFAULT_MODEL")
    llm, fake = fake_llm()

    with pytest.raises(LLMConfigError):
        model_for("trend")
    result = run(collection(*NEWS, *BOK), llm)
    assert result.failure.code == "LLM_CALL_FAILED"
    assert fake.requests == []
