from datetime import date

from fastapi import APIRouter, HTTPException, status

from api.deps import CurrentUserDep, HttpDep, SupabaseDep
from core.config import get_settings
from core.models.exercises import ExerciseSummary
from core.models.workouts import (
    CompleteSession,
    EndChange,
    GeneratePlan,
    LogSet,
    PlanChangeRequest,
    SetLog,
    SwapExercise,
    TodayWorkout,
    WeekPlan,
)
from core.profiles import ProfileNotInHouseholdError, is_own_visible_profile, own_profile_id
from core.workouts import changes as change_service
from core.workouts import plans as service
from core.workouts import rules, tracking

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


@router.get("/me/core-lift-options")
async def core_lift_options(
    today: date, user: CurrentUserDep, supabase: SupabaseDep, search: str | None = None
) -> list[ExerciseSummary]:
    """Compound lifts you can do with your equipment and level, to choose core lifts."""
    profile_id = await own_profile_id(supabase, user.access_token, user.id)
    return await service.core_lift_options(supabase, user.access_token, profile_id, today, search)


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


# --- Doing the workout (Plan for Today) ---------------------------------------------


@router.get("/profiles/{profile_id}/workout-today")
async def workout_today(
    profile_id: str,
    day: date,
    user: CurrentUserDep,
    supabase: SupabaseDep,
    session_id: str | None = None,
) -> TodayWorkout:
    """The workout for `day` (the viewer's local date), or an earlier undone session
    this week by `session_id`; with logged sets, completion and the streak."""
    try:
        is_own = await is_own_visible_profile(supabase, user.access_token, user.id, profile_id)
    except ProfileNotInHouseholdError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile not found") from error
    return await tracking.get_today(
        supabase, user.access_token, profile_id, day, is_own, session_id
    )


@router.put("/me/exercise-logs")
async def log_set(body: LogSet, user: CurrentUserDep, supabase: SupabaseDep) -> SetLog:
    """Save a set (reps, kg or time). Saving the same set again corrects it."""
    profile_id = await own_profile_id(supabase, user.access_token, user.id)
    try:
        return await tracking.log_set(supabase, user.access_token, profile_id, body)
    except tracking.NotYourSessionError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Exercise not in your plan") from error


@router.delete("/me/exercise-logs/{log_id}")
async def delete_set(log_id: str, user: CurrentUserDep, supabase: SupabaseDep) -> None:
    profile_id = await own_profile_id(supabase, user.access_token, user.id)
    await tracking.delete_set(supabase, user.access_token, profile_id, log_id)


@router.post("/me/sessions/{session_id}/complete")
async def complete_session(
    session_id: str, body: CompleteSession, user: CurrentUserDep, supabase: SupabaseDep
) -> TodayWorkout:
    """Mark a workout done, with how hard it felt (sent again: updates the rating)."""
    profile_id = await own_profile_id(supabase, user.access_token, user.id)
    try:
        await tracking.complete(
            supabase, user.access_token, profile_id, session_id, body.done_on, body.effort
        )
    except tracking.NotYourSessionError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not in your plan") from error
    return await tracking.get_today(
        supabase, user.access_token, profile_id, body.done_on, True, session_id
    )


@router.delete("/me/sessions/{session_id}/complete")
async def undo_complete(
    session_id: str, day: date, user: CurrentUserDep, supabase: SupabaseDep
) -> TodayWorkout:
    profile_id = await own_profile_id(supabase, user.access_token, user.id)
    await tracking.undo_complete(supabase, user.access_token, profile_id, session_id)
    return await tracking.get_today(supabase, user.access_token, profile_id, day, True, session_id)


# --- Changing the plan -----------------------------------------------------------------


@router.post("/me/workout-plan/changes")
async def request_change(
    body: PlanChangeRequest, user: CurrentUserDep, supabase: SupabaseDep, http: HttpDep
) -> WeekPlan:
    """Ask for a change (day off, extra or shorter session, vacation, cheat meal,
    medical pause, something else). Returns the week with a preview to apply."""
    profile_id = await own_profile_id(supabase, user.access_token, user.id)
    try:
        return await change_service.request_change(
            supabase, http, get_settings().llm, user.access_token, profile_id, body
        )
    except change_service.ChangeError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    except change_service.NotUnderstoodError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Couldn't turn that into a change. Try one of the other options, or say "
            "which days and what should change.",
        ) from error


@router.post("/me/plan-changes/{change_id}/end")
async def end_change(
    change_id: str, body: EndChange, user: CurrentUserDep, supabase: SupabaseDep, http: HttpDep
) -> WeekPlan:
    """ "I'm back" after a medical pause: previews the rest of the week, lighter."""
    profile_id = await own_profile_id(supabase, user.access_token, user.id)
    try:
        return await change_service.end_medical(
            supabase, http, get_settings().llm, user.access_token, profile_id, change_id, body.today
        )
    except change_service.ChangeError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
