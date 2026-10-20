from typing import Any

from core.models.profiles import HouseholdProfiles, ProfileSummary
from core.supabase import SupabaseClient


def to_household_profiles(rows: list[dict[str, Any]], user_id: str) -> HouseholdProfiles:
    """Mark the signed-in person's own profile and list it first."""
    profiles = [
        ProfileSummary(
            id=row["id"],
            display_name=row["display_name"],
            is_own=row["user_id"] == user_id,
            onboarded=row["onboarded_at"] is not None,
            doing_75_hard=bool(row.get("challenges")),
        )
        for row in rows
    ]
    # Stable sort: own profile first, the rest keep their order.
    profiles.sort(key=lambda profile: not profile.is_own)
    return HouseholdProfiles(profiles=profiles)


class ProfileNotInHouseholdError(Exception):
    """No such profile, or the user isn't allowed to see it."""


async def own_profile_id(supabase: SupabaseClient, token: str, user_id: str) -> str:
    rows = await supabase.select("profiles", {"select": "id", "user_id": f"eq.{user_id}"}, token)
    if not rows:
        raise ProfileNotInHouseholdError
    return rows[0]["id"]


async def is_own_visible_profile(
    supabase: SupabaseClient, token: str, user_id: str, profile_id: str
) -> bool:
    """Whether the profile is the user's own; raises if the user can't see it at all."""
    rows = await supabase.select("profiles", {"select": "user_id", "id": f"eq.{profile_id}"}, token)
    if not rows:
        raise ProfileNotInHouseholdError
    return rows[0]["user_id"] == user_id
