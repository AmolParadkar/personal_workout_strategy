from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes import profiles, settings, seventy_five_hard
from core import __version__
from core.config import get_settings
from core.models.health import HealthResponse
from core.supabase import InvalidValueError, NotSignedInError

app = FastAPI(title="Personal Workout Strategy API", version=__version__)

# Lets the website (a different address from the API) call it from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(profiles.router)
app.include_router(settings.router)
app.include_router(seventy_five_hard.router)


@app.exception_handler(NotSignedInError)
async def not_signed_in(_request: Request, _error: NotSignedInError) -> JSONResponse:
    return JSONResponse({"detail": "Not signed in"}, status.HTTP_401_UNAUTHORIZED)


@app.exception_handler(InvalidValueError)
async def invalid_value(_request: Request, error: InvalidValueError) -> JSONResponse:
    return JSONResponse({"detail": str(error)}, status.HTTP_422_UNPROCESSABLE_CONTENT)


@app.get("/api/health")
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__)
