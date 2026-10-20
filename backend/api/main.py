from fastapi import FastAPI

from core import __version__
from core.models.health import HealthResponse

app = FastAPI(title="Personal Workout Strategy API", version=__version__)


@app.get("/api/health")
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__)
