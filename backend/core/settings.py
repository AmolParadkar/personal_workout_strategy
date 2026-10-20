"""Reading and saving the Settings / Profile page, and finishing onboarding."""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from core.models.settings import (
    DietPreferences,
    DisplaySettings,
    ProfileDetails,
    ProfileSettings,
    TrainingPreferences,
)
from core.supabase import SupabaseClient

# One request fetches the profile and its three one-to-one settings rows.
SETTINGS_SELECT = (
    "id,user_id,display_name,date_of_birth,sex,height_cm,goals,goals_notes,goal_metric,"
    "injuries_notes,onboarded_at,"
    "training_preferences(equipment,available_days,minutes_per_session,location),"
    "diet_preferences(diet_type,cuisines,allergies,dislikes,meals_per_day,cooking_minutes),"
    "display_settings(show_weight,show_calorie_intake,show_calories_burned)"
)

# Which table each section of the page is stored in.
SECTION_TABLES = {
    "training": "training_preferences",
    "diet": "diet_preferences",
    "display": "display_settings",
}


class ProfileNotFoundError(Exception):
    """No such profile, or the user isn't allowed to see it."""


class OnboardingIncompleteError(Exception):
    def __init__(self, missing: list[str]) -> None:
        super().__init__(", ".join(missing))
        self.missing = missing


def to_profile_settings(row: dict[str, Any], user_id: str) -> ProfileSettings:
    return ProfileSettings(
        profile_id=row["id"],
        can_edit=row["user_id"] == user_id,
        profile=ProfileDetails(**row, onboarded=row["onboarded_at"] is not None),
        training=TrainingPreferences(**row["training_preferences"]),
        diet=DietPreferences(**row["diet_preferences"]),
        display=DisplaySettings(**row["display_settings"]),
    )


async def get_profile_settings(
    supabase: SupabaseClient, token: str, user_id: str, profile_id: str
) -> ProfileSettings:
    rows = await supabase.select(
        "profiles", {"select": SETTINGS_SELECT, "id": f"eq.{profile_id}"}, token
    )
    if not rows:
        raise ProfileNotFoundError
    return to_profile_settings(rows[0], user_id)


async def get_own_profile_settings(
    supabase: SupabaseClient, token: str, user_id: str
) -> ProfileSettings:
    rows = await supabase.select(
        "profiles", {"select": SETTINGS_SELECT, "user_id": f"eq.{user_id}"}, token
    )
    if not rows:
        raise ProfileNotFoundError
    return to_profile_settings(rows[0], user_id)


async def update_own_section(
    supabase: SupabaseClient, token: str, user_id: str, section: str, changes: BaseModel
) -> ProfileSettings:
    """Save one section of the signed-in person's settings; only fields sent are changed."""
    values = changes.model_dump(mode="json", exclude_unset=True)
    if values:
        if section == "profile":
            await supabase.update("profiles", {"user_id": f"eq.{user_id}"}, values, token)
        else:
            own = await get_own_profile_settings(supabase, token, user_id)
            await supabase.update(
                SECTION_TABLES[section], {"profile_id": f"eq.{own.profile_id}"}, values, token
            )
    return await get_own_profile_settings(supabase, token, user_id)


def missing_for_onboarding(settings: ProfileSettings) -> list[str]:
    """Fields the first-sign-in questions require before plans can be generated."""
    p, t, d = settings.profile, settings.training, settings.diet
    required = {
        "date_of_birth": p.date_of_birth,
        "sex": p.sex,
        "height_cm": p.height_cm,
        "goals": p.goals,
        "goal_metric": p.goal_metric,
        "available_days": t.available_days,
        "minutes_per_session": t.minutes_per_session,
        "location": t.location,
        "diet_type": d.diet_type,
        "meals_per_day": d.meals_per_day,
    }
    return [name for name, value in required.items() if value in (None, [])]


async def complete_onboarding(
    supabase: SupabaseClient, token: str, user_id: str
) -> ProfileSettings:
    settings = await get_own_profile_settings(supabase, token, user_id)
    missing = missing_for_onboarding(settings)
    if missing:
        raise OnboardingIncompleteError(missing)
    if not settings.profile.onboarded:
        await supabase.update(
            "profiles",
            {"user_id": f"eq.{user_id}"},
            {"onboarded_at": datetime.now(UTC).isoformat()},
            token,
        )
    return await get_own_profile_settings(supabase, token, user_id)
