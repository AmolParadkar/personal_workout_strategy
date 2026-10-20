from datetime import date
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status

from api.deps import CurrentUserDep, SupabaseDep
from core import health_data as service
from core.models.health_data import (
    AddWater,
    HealthConnection,
    IngestRequest,
    IngestResult,
    LogWeight,
    NewHealthConnection,
    WaterDay,
    WeightSummary,
)
from core.profiles import ProfileNotInHouseholdError, is_own_visible_profile, own_profile_id

router = APIRouter(prefix="/api", tags=["health data"])


async def _visible(supabase, user, profile_id: str) -> bool:
    """True for your own profile, False for another visible one; 404 otherwise."""
    try:
        return await is_own_visible_profile(supabase, user.access_token, user.id, profile_id)
    except ProfileNotInHouseholdError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile not found") from error


def _date_error() -> HTTPException:
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT, "Date must be today or yesterday (your local date)"
    )


# --- Apple Health (iOS Shortcut) ---------------------------------------------


@router.post("/ingest/health")
async def ingest_health(
    body: IngestRequest,
    supabase: SupabaseDep,
    authorization: Annotated[str | None, Header()] = None,
) -> IngestResult:
    """Receives Apple Health data from the iOS Shortcut. Authorised by the person's
    connection token (not a sign-in): `Authorization: Bearer wst_...`."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing connection token")
    token = authorization.split(" ", 1)[1].strip()
    valid, skipped = service.validate_samples(body.samples)
    # Called even with nothing valid, so a wrong token is still reported.
    saved = await service.ingest(supabase, token, valid)
    return IngestResult(saved=saved, skipped=skipped)


@router.get("/me/health-connection")
async def health_connection(user: CurrentUserDep, supabase: SupabaseDep) -> HealthConnection:
    profile_id = await own_profile_id(supabase, user.access_token, user.id)
    return await service.get_connection(supabase, user.access_token, profile_id)


@router.post("/me/health-connection")
async def create_health_connection(
    user: CurrentUserDep, supabase: SupabaseDep
) -> NewHealthConnection:
    """Create a connection token for the iOS Shortcut (shown once); cancels any old one."""
    profile_id = await own_profile_id(supabase, user.access_token, user.id)
    return await service.create_connection(supabase, user.access_token, profile_id)


@router.delete("/me/health-connection")
async def remove_health_connection(user: CurrentUserDep, supabase: SupabaseDep) -> HealthConnection:
    profile_id = await own_profile_id(supabase, user.access_token, user.id)
    await service.remove_connection(supabase, user.access_token, profile_id)
    return HealthConnection(connected=False)


# --- Water ---------------------------------------------------------------------


@router.get("/profiles/{profile_id}/water")
async def water_day(
    profile_id: str, day: date, user: CurrentUserDep, supabase: SupabaseDep
) -> WaterDay:
    """Water logged on one day (`day` is the viewer's local date)."""
    is_own = await _visible(supabase, user, profile_id)
    return await service.get_water_day(supabase, user.access_token, profile_id, day, is_own)


@router.post("/me/water")
async def add_water(body: AddWater, user: CurrentUserDep, supabase: SupabaseDep) -> WaterDay:
    """Log a glass. Reaching a gallon (3.8 L) also ticks the 75 Hard water item."""
    profile_id = await own_profile_id(supabase, user.access_token, user.id)
    try:
        return await service.add_water(supabase, user.access_token, profile_id, body.ml, body.date)
    except service.DateOutOfRangeError as error:
        raise _date_error() from error


@router.delete("/me/water/{log_id}")
async def undo_water(
    log_id: str, day: date, user: CurrentUserDep, supabase: SupabaseDep
) -> WaterDay:
    profile_id = await own_profile_id(supabase, user.access_token, user.id)
    return await service.undo_water(supabase, user.access_token, profile_id, log_id, day)


# --- Body weight ---------------------------------------------------------------


@router.get("/profiles/{profile_id}/weight")
async def weight(profile_id: str, user: CurrentUserDep, supabase: SupabaseDep) -> WeightSummary:
    is_own = await _visible(supabase, user, profile_id)
    return await service.get_weight(supabase, user.access_token, profile_id, is_own)


@router.post("/me/weight")
async def log_weight(body: LogWeight, user: CurrentUserDep, supabase: SupabaseDep) -> WeightSummary:
    profile_id = await own_profile_id(supabase, user.access_token, user.id)
    try:
        return await service.log_weight(supabase, user.access_token, profile_id, body.kg, body.date)
    except service.DateOutOfRangeError as error:
        raise _date_error() from error
