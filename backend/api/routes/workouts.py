from datetime import date

from fastapi import APIRouter, HTTPException, status

from api.deps import CurrentUserDep, HttpDep, SupabaseDep
from core.config import get_settings
from core.models.exercises import ExerciseSummary
from core.models.workouts import GeneratePlan, SwapExercise, WeekPlan
from core.profiles import ProfileNotInHouseholdError, is_own_visible_profile, own_profile_id
from core.workouts import plans as service
from core.workouts import rules

router = APIRouter(prefix="/api", tags=["workouts"])


def _monday(week_start: date) -> date:
    if week_start.weekday() != 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "week_start must be a Monday")
    return week_start


@router.get("/profiles/{profile_id}/workout-plan")
async def week_plan(
    profile_id: str, week_start: date, user: CurrentUserDep, supabase: SupabaseDep
) -> WeekPlan:
    """A person's plan for a week (active, plus a draft preview on your own)."""
    try:
        is_own = await is_own_visible_profile(supabase, user.access_token, user.id, profile_id)
    except ProfileNotInHouseholdError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile not found") from error
    return await service.get_week(
        supabase, user.access_token, profile_id, _monday(week_start), is_own
    )


@router.post("/me/workout-plan/generate")
async def generate(
    body: GeneratePlan, user: CurrentUserDep, supabase: SupabaseDep, http: HttpDep
) -> WeekPlan:
    """Make this week's plan (from `today` on). With reason `new_week` nothing
    happens if the week already has one. Tried straight away; otherwise the Mac
    worker makes it (`generating` is true until then)."""
    profile_id = await own_profile_id(supabase, user.access_token, user.id)
    return await service.generate(
        supabase, http, get_settings().llm, user.access_token, profile_id, body.today, body.reason
    )


@router.post("/me/workout-plans/{plan_id}/apply")
async def apply(plan_id: str, user: CurrentUserDep, supabase: SupabaseDep) -> WeekPlan:
    """Use the previewed draft as the week's plan."""
    try:
        await service.apply_draft(supabase, user.access_token, plan_id)
    except service.PlanNotFoundError as error:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No draft plan of yours with that id"
        ) from error
    return await _own_week_of_plan(supabase, user, plan_id)


@router.delete("/me/workout-plans/{plan_id}")
async def discard(plan_id: str, user: CurrentUserDep, supabase: SupabaseDep) -> WeekPlan:
    """Throw away a draft (keep the current plan)."""
    profile_id = await own_profile_id(supabase, user.access_token, user.id)
    rows = await supabase.select(
        "workout_plans", {"select": "week_start", "id": f"eq.{plan_id}"}, user.access_token
    )
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plan not found")
    await service.discard_draft(supabase, user.access_token, profile_id, plan_id)
    return await service.get_week(
        supabase, user.access_token, profile_id, date.fromisoformat(rows[0]["week_start"]), True
    )


async def _own_week_of_plan(supabase, user, plan_id: str) -> WeekPlan:
    profile_id = await own_profile_id(supabase, user.access_token, user.id)
    rows = await supabase.select(
        "workout_plans", {"select": "week_start", "id": f"eq.{plan_id}"}, user.access_token
    )
    week_start = (
        date.fromisoformat(rows[0]["week_start"]) if rows else rules.week_start_of(date.today())
    )
    return await service.get_week(supabase, user.access_token, profile_id, week_start, True)


@router.get("/me/session-items/{item_id}/alternatives")
async def alternatives(
    item_id: str, user: CurrentUserDep, supabase: SupabaseDep
) -> list[ExerciseSummary]:
    """Swaps for an exercise in your plan: same phase and muscles, your equipment."""
    profile_id = await own_profile_id(supabase, user.access_token, user.id)
    try:
        return await service.alternatives(supabase, user.access_token, profile_id, item_id)
    except service.PlanNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Exercise not in your plan") from error


@router.put("/me/session-items/{item_id}/exercise")
async def swap(
    item_id: str, body: SwapExercise, user: CurrentUserDep, supabase: SupabaseDep
) -> WeekPlan:
    """Swap an exercise for one of its alternatives."""
    profile_id = await own_profile_id(supabase, user.access_token, user.id)
    try:
        await service.swap(supabase, user.access_token, profile_id, item_id, body.exercise_id)
    except service.PlanNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Exercise not in your plan") from error
    except service.NotAnAlternativeError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Pick one of the suggested swaps"
        ) from error
    rows = await supabase.select(
        "session_items",
        {"select": "workout_sessions(workout_plans(id))", "id": f"eq.{item_id}"},
        user.access_token,
    )
    plan_id = rows[0]["workout_sessions"]["workout_plans"]["id"]
    return await _own_week_of_plan(supabase, user, plan_id)
