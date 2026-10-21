"""Reading what a plan needs (profile, training settings, the exercise library),
with whoever's access is calling: the signed-in person (API) or the worker."""

from collections.abc import Awaitable, Callable
from datetime import date
from typing import Any

from core.supabase import SupabaseClient
from core.workouts.generate import PlanInputs

LIBRARY_COLUMNS = (
    "id,name,category,equipment,level,mechanic,force,primary_muscles,secondary_muscles"
)

Select = Callable[[str, dict[str, str]], Awaitable[list[dict[str, Any]]]]


def _age(born: str | None, today: date) -> int | None:
    if not born:
        return None
    b = date.fromisoformat(born)
    return today.year - b.year - ((today.month, today.day) < (b.month, b.day))


async def load_inputs(select: Select, profile_id: str, week_start: date, today: date) -> PlanInputs:
    """Everything a plan needs, read with the caller's access (user or worker)."""
    profile = (
        await select(
            "profiles",
            {"select": "sex,date_of_birth,goals,injuries_notes", "id": f"eq.{profile_id}"},
        )
    )[0]
    training = (
        await select(
            "training_preferences",
            {
                "select": "equipment,available_days,minutes_per_session,location,experience",
                "profile_id": f"eq.{profile_id}",
            },
        )
    )[0]
    library = await select("exercises", {"select": LIBRARY_COLUMNS, "limit": "2000"})
    return PlanInputs(
        profile_id=profile_id,
        week_start=week_start,
        today=today,
        goals=profile.get("goals") or [],
        experience=training.get("experience") or "beginner",
        available_days=training.get("available_days") or [],
        minutes_per_session=training.get("minutes_per_session") or 45,
        equipment=training.get("equipment") or [],
        location=training.get("location"),
        sex=profile.get("sex"),
        age=_age(profile.get("date_of_birth"), today),
        injuries=profile.get("injuries_notes"),
        library=library,
    )


def user_select(supabase: SupabaseClient, token: str) -> Select:
    async def select(table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        return await supabase.select(table, params, token)

    return select


async def status_to_save(
    select: Select, profile_id: str, week_start: date, wanted: str, reason: str
) -> str | None:
    """Checked again just before saving, because another request (a page reload,
    the worker) may have made a plan meanwhile: an automatic new-week plan is
    dropped if the week now has one, and a plan meant to be active becomes a
    draft (preview) rather than silently replacing it. None means don't save."""
    active = await select(
        "workout_plans",
        {
            "select": "id",
            "profile_id": f"eq.{profile_id}",
            "week_start": f"eq.{week_start.isoformat()}",
            "status": "eq.active",
        },
    )
    if not active:
        return wanted
    return None if reason == "new_week" else "draft"
