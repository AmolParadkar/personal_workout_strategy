from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import profiles
from core import __version__
from core.config import get_settings
from core.models.health import HealthResponse

app = FastAPI(title="Personal Workout Strategy API", version=__version__)

# Lets the website (a different address from the API) call it from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(profiles.router)


@app.get("/api/health")
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__)
