from fastapi import APIRouter, HTTPException, status

from api.deps import CurrentUserDep, SupabaseDep
from core.models.profiles import HouseholdProfiles
from core.profiles import to_household_profiles
from core.supabase import NotSignedInError

router = APIRouter(prefix="/api/me", tags=["profiles"])


@router.get("/profiles")
async def household_profiles(user: CurrentUserDep, supabase: SupabaseDep) -> HouseholdProfiles:
    """Profiles in the signed-in person's household, own profile first."""
    try:
        rows = await supabase.get_household_profiles(user.access_token)
    except NotSignedInError as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in") from error
    return to_household_profiles(rows, user.id)
