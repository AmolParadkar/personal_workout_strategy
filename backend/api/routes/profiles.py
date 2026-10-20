from fastapi import APIRouter

from api.deps import CurrentUserDep, SupabaseDep
from core.models.profiles import HouseholdProfiles
from core.profiles import to_household_profiles

router = APIRouter(prefix="/api/me", tags=["profiles"])


@router.get("/profiles")
async def household_profiles(user: CurrentUserDep, supabase: SupabaseDep) -> HouseholdProfiles:
    """Profiles in the signed-in person's household, own profile first."""
    rows = await supabase.get_household_profiles(user.access_token)
    return to_household_profiles(rows, user.id)
