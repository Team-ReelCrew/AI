from pydantic import BaseModel, ConfigDict, NonNegativeFloat, NonNegativeInt


class LLMCallRecord(BaseModel):
    """LLM 호출 1회의 비용·시간 기록. 단일 에이전트·고정 파이프라인과 비교할 때 쓴다."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    agent: str
    requested_model: str
    served_model: str
    input_tokens: NonNegativeInt
    output_tokens: NonNegativeInt
    cached_input_tokens: NonNegativeInt = 0
    reasoning_tokens: NonNegativeInt = 0
    duration_seconds: NonNegativeFloat
    status: str | None = None
