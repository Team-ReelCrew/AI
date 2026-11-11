from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

IDENTIFIER_PATTERN = r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}$"
JobStatus = Literal["queued", "running", "succeeded", "failed"]
Result = TypeVar("Result")


class JobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    job_id: str = Field(alias="jobId", pattern=IDENTIFIER_PATTERN)
    domain: Literal["economy"]
    template_id: str = Field(alias="templateId", pattern=IDENTIFIER_PATTERN)


class JobAccepted(BaseModel):
    job_id: str = Field(serialization_alias="jobId")
    status: JobStatus


class CardImage(BaseModel):
    order: int
    image_url: str = Field(serialization_alias="imageUrl")


class Source(BaseModel):
    title: str
    url: str


class CardNewsOutput(BaseModel):
    cards: list[CardImage]
    caption: str
    sources: list[Source]


class JobFailure(BaseModel):
    stage: str
    code: str
    message: str


class JobDetail(JobAccepted):
    stage: str | None = None
    output: CardNewsOutput | None = None
    failure: JobFailure | None = None


class FieldError(BaseModel):
    field: str
    message: str


class ApiError(BaseModel):
    details: list[FieldError] = Field(default_factory=list)


class ApiResponse(BaseModel, Generic[Result]):
    is_success: bool = Field(serialization_alias="isSuccess")
    code: str
    message: str
    result: Result | None = None
    error: ApiError | None = None
