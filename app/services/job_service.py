from dataclasses import dataclass, replace
from pathlib import Path
from threading import Lock

from app.schemas.job import JobFailure, JobRequest, JobStatus

SAMPLE_CARD_DIRECTORY = Path(__file__).resolve().parents[1] / "assets" / "sample-cards"
SAMPLE_CARD_FILES = tuple(f"card-{number:02}.jpg" for number in range(1, 6))
SAMPLE_STAGE = "sample"


@dataclass(frozen=True)
class Job:
    request: JobRequest
    status: JobStatus = "queued"
    stage: str | None = None
    failure: JobFailure | None = None


class JobIdConflict(Exception):
    pass


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = Lock()

    def register(self, request: JobRequest) -> tuple[Job, bool]:
        with self._lock:
            existing = self._jobs.get(request.job_id)
            if existing is not None:
                if existing.request != request:
                    raise JobIdConflict(request.job_id)
                return existing, False

            job = Job(request=request)
            self._jobs[request.job_id] = job
            return job, True

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def prepare_sample(self, job_id: str) -> None:
        with self._lock:
            job = replace(self._jobs[job_id], status="running", stage=SAMPLE_STAGE)
            self._jobs[job_id] = job

        try:
            files_available = all(
                (SAMPLE_CARD_DIRECTORY / filename).is_file()
                for filename in SAMPLE_CARD_FILES
            )
        except OSError:
            files_available = False

        if files_available:
            completed = replace(job, status="succeeded", stage=None)
        else:
            failure = JobFailure(
                stage=SAMPLE_STAGE,
                code="SAMPLE_CARD_UNAVAILABLE",
                message="샘플 카드 파일을 사용할 수 없습니다.",
            )
            completed = replace(job, status="failed", stage=None, failure=failure)

        with self._lock:
            self._jobs[job_id] = completed
