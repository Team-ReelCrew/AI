import os
from time import perf_counter
from typing import Any, TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.schemas.llm import LLMCallRecord

DEFAULT_MODEL_ENV = "REELCREW_DEFAULT_MODEL"
DEFAULT_MAX_OUTPUT_TOKENS = 16000

Output = TypeVar("Output", bound=BaseModel)


class LLMConfigError(Exception):
    pass


class LLMOutputError(Exception):
    def __init__(self, agent: str, reason: str) -> None:
        self.agent = agent
        self.reason = reason
        super().__init__(f"{agent}: {reason}")


def model_for(agent: str) -> str:
    """에이전트별 모델을 환경변수에서 읽는다.

    REELCREW_TREND_MODEL처럼 에이전트 전용 값이 있으면 쓰고, 없으면 REELCREW_DEFAULT_MODEL을 쓴다.
    에이전트마다 다른 모델을 지정해 모델 라우팅의 비용 차이를 비교할 수 있다.
    """
    model = os.environ.get(f"REELCREW_{agent.upper()}_MODEL") or os.environ.get(
        DEFAULT_MODEL_ENV
    )
    if not model:
        raise LLMConfigError(
            f"{agent} 에이전트의 모델이 없습니다. .env에 {DEFAULT_MODEL_ENV}를 설정하세요."
        )
    return model


class StructuredLLM:
    """OpenAI Responses API의 구조화 출력 호출을 감싸고, 호출마다 토큰과 시간을 기록한다."""

    def __init__(self, client: Any | None = None) -> None:
        self._client = client
        self.calls: list[LLMCallRecord] = []

    @property
    def client(self) -> Any:
        # OPENAI_API_KEY가 없으면 생성 시 오류가 나므로 첫 호출 때 만든다.
        if self._client is None:
            self._client = AsyncOpenAI()
        return self._client

    async def parse(
        self,
        *,
        agent: str,
        system: str,
        prompt: str,
        output_type: type[Output],
        max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    ) -> Output:
        model = model_for(agent)
        started = perf_counter()
        response = await self.client.responses.parse(
            model=model,
            instructions=system,
            input=prompt,
            text_format=output_type,
            max_output_tokens=max_output_tokens,
            store=False,
        )

        usage = response.usage
        input_details = getattr(usage, "input_tokens_details", None)
        output_details = getattr(usage, "output_tokens_details", None)
        self.calls.append(
            LLMCallRecord(
                agent=agent,
                requested_model=model,
                served_model=response.model,
                input_tokens=usage.input_tokens if usage else 0,
                output_tokens=usage.output_tokens if usage else 0,
                cached_input_tokens=getattr(input_details, "cached_tokens", 0) or 0,
                reasoning_tokens=getattr(output_details, "reasoning_tokens", 0) or 0,
                duration_seconds=perf_counter() - started,
                status=response.status,
            )
        )

        if response.status == "incomplete":
            reason = getattr(response.incomplete_details, "reason", None) or "unknown"
            raise LLMOutputError(agent, f"응답이 완료되지 않았습니다: {reason}")
        for item in response.output:
            if item.type == "message":
                for content in item.content:
                    if content.type == "refusal":
                        raise LLMOutputError(agent, f"모델이 거절했습니다: {content.refusal}")

        parsed = response.output_parsed
        if parsed is None:
            raise LLMOutputError(agent, "구조화 출력을 읽을 수 없습니다.")
        return parsed
