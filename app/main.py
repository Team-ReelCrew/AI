from fastapi import FastAPI

app = FastAPI(title="ReelCrew AI")


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
