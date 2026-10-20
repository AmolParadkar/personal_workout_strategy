from typing import Any

from core.models.profiles import HouseholdProfiles, ProfileSummary


def to_household_profiles(rows: list[dict[str, Any]], user_id: str) -> HouseholdProfiles:
    """Mark the signed-in person's own profile and list it first."""
    profiles = [
        ProfileSummary(
            id=row["id"],
            display_name=row["display_name"],
            is_own=row["user_id"] == user_id,
            onboarded=row["onboarded_at"] is not None,
        )
        for row in rows
    ]
    # Stable sort: own profile first, the rest keep their order.
    profiles.sort(key=lambda profile: not profile.is_own)
    return HouseholdProfiles(profiles=profiles)
