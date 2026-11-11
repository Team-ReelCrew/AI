from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Path, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.schemas.job import (
    IDENTIFIER_PATTERN,
    ApiError,
    ApiResponse,
    CardImage,
    CardNewsOutput,
    FieldError,
    JobAccepted,
    JobDetail,
    JobRequest,
    Source,
)
from app.services.job_service import SAMPLE_CARD_FILES, JobIdConflict, JobStore

SAMPLE_CARDS_ROUTE = "sample-cards"
SAMPLE_CARDS_PATH = "/api/v1/internal/sample-cards"

router = APIRouter(
    prefix="/api/v1/internal/jobs",
    tags=["jobs"],
    responses={422: {"model": ApiResponse[None], "description": "잘못된 요청"}},
)
jobs = JobStore()


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: list[FieldError] | None = None,
) -> JSONResponse:
    response = ApiResponse[None](
        is_success=False,
        code=code,
        message=message,
        error=ApiError(details=details or []),
    )
    return JSONResponse(
        status_code=status_code, content=response.model_dump(mode="json", by_alias=True)
    )


async def invalid_request(
    _request: Request, exception: RequestValidationError
) -> JSONResponse:
    details = [
        FieldError(
            field=".".join(str(part) for part in error["loc"]),
            message=error["msg"],
        )
        for error in exception.errors()
    ]
    return error_response(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "INVALID_REQUEST",
        "제작 작업 요청의 형식이 올바르지 않습니다.",
        details,
    )


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ApiResponse[JobAccepted],
    responses={
        200: {"model": ApiResponse[JobAccepted], "description": "기존 작업 반환"},
        409: {"model": ApiResponse[None], "description": "작업 ID 충돌"},
    },
)
def register_job(
    payload: JobRequest, background_tasks: BackgroundTasks, response: Response
) -> ApiResponse[JobAccepted] | JSONResponse:
    try:
        job, created = jobs.register(payload)
    except JobIdConflict:
        return error_response(
            status.HTTP_409_CONFLICT,
            "JOB_ID_CONFLICT",
            "같은 작업 ID에 다른 입력이 이미 등록되어 있습니다.",
        )

    result = JobAccepted(job_id=payload.job_id, status=job.status)
    if created:
        background_tasks.add_task(jobs.prepare_sample, payload.job_id)
        return ApiResponse[JobAccepted](
            is_success=True,
            code="JOB_ACCEPTED",
            message="제작 작업을 접수했습니다.",
            result=result,
        )

    response.status_code = status.HTTP_200_OK
    return ApiResponse[JobAccepted](
        is_success=True,
        code="JOB_EXISTS",
        message="이미 등록된 제작 작업입니다.",
        result=result,
    )


@router.get(
    "/{jobId}",
    response_model=ApiResponse[JobDetail],
    responses={404: {"model": ApiResponse[None], "description": "작업 ID를 찾을 수 없음"}},
)
def get_job(
    job_id: Annotated[str, Path(alias="jobId", pattern=IDENTIFIER_PATTERN)],
    request: Request,
) -> ApiResponse[JobDetail] | JSONResponse:
    job = jobs.get(job_id)
    if job is None:
        return error_response(
            status.HTTP_404_NOT_FOUND, "JOB_NOT_FOUND", "제작 작업을 찾을 수 없습니다."
        )

    output = None
    if job.status == "succeeded":
        output = CardNewsOutput(
            cards=[
                CardImage(
                    order=order,
                    image_url=str(request.url_for(SAMPLE_CARDS_ROUTE, path=filename)),
                )
                for order, filename in enumerate(SAMPLE_CARD_FILES, start=1)
            ],
            caption="ReelCrew 제작 API 연동용 샘플 카드뉴스입니다.",
            sources=[Source(title="예시 경제 자료", url="https://example.com/economy")],
        )

    return ApiResponse[JobDetail](
        is_success=True,
        code="JOB_FOUND",
        message="제작 작업을 조회했습니다.",
        result=JobDetail(
            job_id=job_id,
            status=job.status,
            stage=job.stage,
            output=output,
            failure=job.failure,
        ),
    )
