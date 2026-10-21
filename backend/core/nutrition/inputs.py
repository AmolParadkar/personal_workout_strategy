"""Reading what a meal plan needs, with whoever's access is calling (the signed-in
person on the API, or the worker): profile and diet settings, the latest weigh-in
and recent steps, the week's training from the workout plan, last week's mains
and the foods the planner can use."""

from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from typing import Any

from core.nutrition.generate import MealInputs
from core.nutrition.targets import Body

Select = Callable[[str, dict[str, str]], Awaitable[list[dict[str, Any]]]]

FOOD_COLUMNS = (
    "id,name,alias,source,role,diet,basis,serving_label,serving_g,countable,kcal,protein_g,"
    "carbs_g,fat_g,fibre_g,micros,ingredients"
)
STEP_DAYS = 14
MIN_STEP_DAYS = 5


class MissingDetailsError(Exception):
    """Something the targets need isn't saved yet (e.g. a weigh-in)."""

    def __init__(self, missing: list[str]):
        super().__init__(", ".join(missing))
        self.missing = missing


def _age(born: str, today: date) -> int:
    b = date.fromisoformat(born)
    return today.year - b.year - ((today.month, today.day) < (b.month, b.day))


async def latest_weight(select: Select, profile_id: str) -> float | None:
    rows = await select(
        "health_samples",
        {
            "select": "value",
            "profile_id": f"eq.{profile_id}",
            "metric": "eq.weight_kg",
            "value": "not.is.null",
            "order": "recorded_on.desc,updated_at.desc",
            "limit": "1",
        },
    )
    return float(rows[0]["value"]) if rows else None


async def missing_details(select: Select, profile_id: str) -> list[str]:
    """What's needed before targets can be worked out: 'weight', and profile
    fields normally filled in at the welcome."""
    profile = (
        await select(
            "profiles",
            {"select": "date_of_birth,height_cm", "id": f"eq.{profile_id}"},
        )
    )[0]
    missing = [k for k in ("date_of_birth", "height_cm") if not profile.get(k)]
    if await latest_weight(select, profile_id) is None:
        missing.append("weight")
    return missing


async def load_inputs(
    select: Select, profile_id: str, week_start: date, today: date, seed: str = ""
) -> MealInputs:
    profile = (
        await select(
            "profiles",
            {"select": "sex,date_of_birth,height_cm,goals,household_id", "id": f"eq.{profile_id}"},
        )
    )[0]
    weight = await latest_weight(select, profile_id)
    missing = [k for k in ("date_of_birth", "height_cm") if not profile.get(k)]
    if weight is None:
        missing.append("weight")
    if missing:
        raise MissingDetailsError(missing)

    steps = await select(
        "health_samples",
        {
            "select": "value",
            "profile_id": f"eq.{profile_id}",
            "metric": "eq.steps",
            "recorded_on": f"gte.{(today - timedelta(days=STEP_DAYS)).isoformat()}",
            "value": "not.is.null",
        },
    )
    counts = [float(r["value"]) for r in steps]
    avg_steps = round(sum(counts) / len(counts)) if len(counts) >= MIN_STEP_DAYS else None

    diet = (
        await select(
            "diet_preferences",
            {
                "select": "diet_type,cuisines,allergies,dislikes,meals_per_day,cooking_minutes",
                "profile_id": f"eq.{profile_id}",
            },
        )
        or [{}]
    )[0]

    workouts = await select(
        "workout_plans",
        {
            "select": "workout_sessions(day,minutes)",
            "profile_id": f"eq.{profile_id}",
            "week_start": f"eq.{week_start.isoformat()}",
            "status": "eq.active",
        },
    )
    training: dict[date, int] = {}
    for plan in workouts:
        for session in plan.get("workout_sessions") or []:
            training[date.fromisoformat(session["day"])] = int(session["minutes"])

    last_week = await select(
        "meal_plans",
        {
            "select": "planned_meals(slot,items)",
            "profile_id": f"eq.{profile_id}",
            "week_start": f"eq.{(week_start - timedelta(days=7)).isoformat()}",
            "status": "eq.active",
        },
    )
    recent = {
        meal["items"][0]["food_id"]
        for plan in last_week
        for meal in plan.get("planned_meals") or []
        if meal["slot"] in ("lunch", "dinner") and meal.get("items")
    }

    # The shared databases plus this household's own dishes (the worker sees every
    # household's, so it's filtered here too).
    household = profile.get("household_id")
    foods = await select(
        "foods",
        {
            "select": FOOD_COLUMNS,
            "role": "not.is.null",
            "or": f"(household_id.is.null,household_id.eq.{household})"
            if household
            else "(household_id.is.null)",
            "limit": "3000",
        },
    )
    return MealInputs(
        profile_id=profile_id,
        week_start=week_start,
        today=today,
        body=Body(
            weight_kg=weight,
            height_cm=float(profile["height_cm"]),
            age=_age(profile["date_of_birth"], today),
            sex=profile.get("sex"),
            goals=profile.get("goals") or [],
            avg_steps=avg_steps,
        ),
        diet_type=diet.get("diet_type"),
        cuisines=diet.get("cuisines") or [],
        allergies=diet.get("allergies") or [],
        dislikes=diet.get("dislikes") or [],
        meals_per_day=diet.get("meals_per_day"),
        cooking_minutes=diet.get("cooking_minutes"),
        training=training,
        foods=foods,
        seed=seed,
        recent=recent,
    )


PLAN_WITH_MEALS = (
    "id,week_start,daily_targets(day,kcal,protein_g,carbs_g,fat_g,fibre_g,micros,reasons,"
    "training_minutes),planned_meals(day,slot,position,kind,name,items,nutrients,note)"
)


async def kept_days(
    select: Select, profile_id: str, week_start: date, today: date
) -> list[dict[str, Any]]:
    """Days before today from this week's current plan, kept as they were."""
    rows = await select(
        "meal_plans",
        {
            "select": PLAN_WITH_MEALS,
            "profile_id": f"eq.{profile_id}",
            "week_start": f"eq.{week_start.isoformat()}",
            "status": "eq.active",
        },
    )
    if not rows:
        return []
    plan = rows[0]
    kept = []
    for target in plan.get("daily_targets") or []:
        if target["day"] >= today.isoformat():
            continue
        meals = sorted(
            (m for m in plan.get("planned_meals") or [] if m["day"] == target["day"]),
            key=lambda m: m["position"],
        )
        kept.append(
            {
                "day": target["day"],
                "targets": {k: v for k, v in target.items() if k != "day"},
                "meals": [{k: v for k, v in m.items() if k != "day"} for m in meals],
            }
        )
    return kept


def merge_kept(kept: list[dict[str, Any]], plan: dict[str, Any]) -> dict[str, Any]:
    kept_days_ = {d["day"] for d in kept}
    days = kept + [d for d in plan["days"] if d["day"] not in kept_days_]
    return {**plan, "days": sorted(days, key=lambda d: d["day"])}


async def status_to_save(
    select: Select, profile_id: str, week_start: date, wanted: str, reason: str
) -> str | None:
    """Checked just before saving (another request may have made a plan
    meanwhile): an automatic new-week plan is dropped if the week now has one,
    and a plan meant to be active becomes a draft. None: don't save."""
    active = await select(
        "meal_plans",
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
