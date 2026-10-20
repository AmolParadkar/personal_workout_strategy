from fastapi import APIRouter, HTTPException, status

from api.deps import CurrentUserDep, SupabaseDep
from core import seventy_five_hard as service
from core.models.seventy_five_hard import SetCheck, SeventyFiveHardState, StartChallenge
from core.profiles import ProfileNotInHouseholdError, is_own_visible_profile, own_profile_id

router = APIRouter(prefix="/api", tags=["75 Hard"])


@router.get("/profiles/{profile_id}/seventy-five-hard")
async def seventy_five_hard_state(
    profile_id: str, user: CurrentUserDep, supabase: SupabaseDep
) -> SeventyFiveHardState:
    """The 75 Hard page for any profile in the household; editable only for your own."""
    try:
        is_own = await is_own_visible_profile(supabase, user.access_token, user.id, profile_id)
    except ProfileNotInHouseholdError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile not found") from error
    return await service.get_state(supabase, user.access_token, profile_id, can_edit=is_own)


@router.post("/me/seventy-five-hard/start")
async def start_challenge(
    body: StartChallenge, user: CurrentUserDep, supabase: SupabaseDep
) -> SeventyFiveHardState:
    profile_id = await own_profile_id(supabase, user.access_token, user.id)
    try:
        return await service.start(
            supabase, user.access_token, profile_id, body.current_day, body.timezone
        )
    except service.ChallengeAlreadyRunningError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, "A challenge is already running") from error
    except service.UnknownTimezoneError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown timezone: {body.timezone}"
        ) from error


@router.post("/me/seventy-five-hard/stop")
async def stop_challenge(user: CurrentUserDep, supabase: SupabaseDep) -> SeventyFiveHardState:
    profile_id = await own_profile_id(supabase, user.access_token, user.id)
    try:
        return await service.stop(supabase, user.access_token, profile_id)
    except service.NoRunningChallengeError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, "No challenge is running") from error


@router.put("/me/seventy-five-hard/checks")
async def set_check(
    body: SetCheck, user: CurrentUserDep, supabase: SupabaseDep
) -> SeventyFiveHardState:
    """Tick or untick one item for today (or yesterday, until noon)."""
    profile_id = await own_profile_id(supabase, user.access_token, user.id)
    try:
        return await service.set_check(
            supabase, user.access_token, profile_id, body.date, body.item, body.checked
        )
    except service.NoRunningChallengeError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, "No challenge is running") from error
    except service.DayNotEditableError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Only today, and yesterday until noon, can be changed",
        ) from error
