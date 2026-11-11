from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles

from app.api.routes.jobs import (
    SAMPLE_CARDS_PATH,
    SAMPLE_CARDS_ROUTE,
    invalid_request,
    router,
)
from app.services.job_service import SAMPLE_CARD_DIRECTORY

app = FastAPI(title="ReelCrew AI")
app.include_router(router)
app.add_exception_handler(RequestValidationError, invalid_request)
app.mount(
    SAMPLE_CARDS_PATH,
    StaticFiles(directory=SAMPLE_CARD_DIRECTORY),
    name=SAMPLE_CARDS_ROUTE,
)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
