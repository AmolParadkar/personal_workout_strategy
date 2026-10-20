from fastapi import APIRouter, HTTPException, status

from api.deps import CurrentUserDep, HttpDep, SupabaseDep
from core import connections as service
from core.config import get_settings
from core.connectors.keys import InvalidStateError
from core.health_data import DateOutOfRangeError, check_local_date
from core.models.connections import (
    CompleteConnection,
    Connections,
    Service,
    ServiceSyncResult,
    StartConnection,
    StartedConnection,
    SyncRequest,
    SyncResult,
)
from core.profiles import ProfileNotInHouseholdError, is_own_visible_profile, own_profile_id

router = APIRouter(prefix="/api", tags=["connections"])


def _not_available() -> HTTPException:
    return HTTPException(
        status.HTTP_409_CONFLICT,
        "This service isn’t set up on the server yet (developer app keys).",
    )


def _check_today(today) -> None:
    try:
        check_local_date(today)
    except DateOutOfRangeError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Date must be today (your local date)"
        ) from error


@router.get("/profiles/{profile_id}/connections")
async def connections(profile_id: str, user: CurrentUserDep, supabase: SupabaseDep) -> Connections:
    """Which services a person has connected (view-only on the other person's profile)."""
    try:
        is_own = await is_own_visible_profile(supabase, user.access_token, user.id, profile_id)
    except ProfileNotInHouseholdError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile not found") from error
    return await service.list_connections(
        supabase, get_settings(), user.access_token, profile_id, is_own
    )


@router.post("/me/connections/{name}/start")
async def start_connection(
    name: Service, body: StartConnection, user: CurrentUserDep, supabase: SupabaseDep
) -> StartedConnection:
    """The service's sign-in address to send the person to."""
    profile_id = await own_profile_id(supabase, user.access_token, user.id)
    try:
        return service.start(get_settings(), profile_id, name, body.redirect_uri)
    except service.ServiceNotAvailableError as error:
        raise _not_available() from error
    except service.BadRedirectError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown return address"
        ) from error


@router.post("/me/connections/{name}/complete")
async def complete_connection(
    name: Service,
    body: CompleteConnection,
    user: CurrentUserDep,
    supabase: SupabaseDep,
    http: HttpDep,
) -> ServiceSyncResult:
    """Finish connecting with the code the service sent back, then fetch the last 30 days."""
    _check_today(body.today)
    profile_id = await own_profile_id(supabase, user.access_token, user.id)
    try:
        return await service.complete(
            supabase,
            http,
            get_settings(),
            user.access_token,
            profile_id,
            name,
            body.code,
            body.state,
            body.redirect_uri,
            body.today,
        )
    except service.ServiceNotAvailableError as error:
        raise _not_available() from error
    except (InvalidStateError, service.BadRedirectError) as error:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "This sign-in link has expired. Please try again."
        ) from error
    except service.ConnectFailedError as error:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "The service didn’t accept the sign-in. Please try again."
        ) from error


@router.delete("/me/connections/{name}")
async def disconnect(
    name: Service, user: CurrentUserDep, supabase: SupabaseDep, http: HttpDep
) -> Connections:
    profile_id = await own_profile_id(supabase, user.access_token, user.id)
    settings = get_settings()
    await service.disconnect(supabase, http, settings, user.access_token, profile_id, name)
    return await service.list_connections(supabase, settings, user.access_token, profile_id, True)


@router.post("/me/connections/sync")
async def sync(
    body: SyncRequest, user: CurrentUserDep, supabase: SupabaseDep, http: HttpDep
) -> SyncResult:
    """Fetch new data from your connections. Without `force`, only those not synced
    in the last 3 hours (the website calls this when it opens)."""
    _check_today(body.today)
    profile_id = await own_profile_id(supabase, user.access_token, user.id)
    settings = get_settings()
    results = await service.sync(
        supabase,
        http,
        settings,
        user.access_token,
        profile_id,
        body.today,
        body.force,
        body.service,
    )
    connections = await service.list_connections(
        supabase, settings, user.access_token, profile_id, True
    )
    return SyncResult(results=results, connections=connections)
