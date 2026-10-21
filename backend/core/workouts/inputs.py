"""Reading what a plan needs, with whoever's access is calling: the signed-in
person (API) or the worker. Profile and training settings, the exercise library,
core lifts, the 6-week block, changes in effect (days off, vacation, medical
pause, …) and what was lifted last time (for progressive overload)."""

from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from typing import Any

from core.supabase import SupabaseClient
from core.workouts import overload
from core.workouts.generate import BLOCK_WEEKS, Adjustments, PlanInputs

LIBRARY_COLUMNS = (
    "id,name,category,equipment,level,mechanic,force,primary_muscles,secondary_muscles"
)
HISTORY_WEEKS = 8
ITEM_FIELDS = (
    "phase,position,exercise_id,sets,reps_min,reps_max,duration_seconds,rest_seconds,"
    "target_load_kg,notes"
)

Select = Callable[[str, dict[str, str]], Awaitable[list[dict[str, Any]]]]


def _age(born: str | None, today: date) -> int | None:
    if not born:
        return None
    b = date.fromisoformat(born)
    return today.year - b.year - ((today.month, today.day) < (b.month, b.day))


def _days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=n) for n in range((end - start).days + 1)]


# --- Changes in effect --------------------------------------------------------------


def adjustments(changes: list[dict[str, Any]], week_start: date, today: date) -> Adjustments:
    """Turn the plan changes overlapping this week into concrete days and settings."""
    week_end = week_start + timedelta(days=6)
    adj = Adjustments()
    for change in changes:
        start = date.fromisoformat(change["start_date"])
        end = date.fromisoformat(change["end_date"]) if change.get("end_date") else None
        kind = change["kind"]
        in_week = [d for d in _days(max(start, week_start), min(end or week_end, week_end))]
        if kind == "day_off":
            adj.days_off |= set(in_week)
        elif kind == "add_session" and week_start <= start <= week_end:
            adj.extra_days.add(start)
        elif kind == "shorter" and week_start <= start <= week_end and change.get("minutes"):
            adj.minutes[start] = change["minutes"]
        elif kind == "vacation" and in_week:
            if change.get("vacation_mode") == "travel":
                adj.travel_days |= set(in_week)
                adj.notes.append("Away from home some days: short bodyweight and band sessions.")
            else:
                adj.days_off |= set(in_week)
                adj.notes.append("On vacation some days: no training then.")
        elif kind == "cheat_meal" and week_start <= start <= week_end:
            if change.get("cheat_mode") == "spread":
                adj.spread_after.append(start)
                adj.notes.append(
                    "A cheat meal this week: a little extra cardio spread over the "
                    "following sessions."
                )
        elif kind == "medical":
            if in_week and (end is None or end >= week_start):
                paused = [d for d in in_week if end is None or d <= end]
                adj.days_off |= set(paused)
                if paused:
                    adj.notes.append("Paused for a medical reason: no training on those days.")
            # The first week back is lighter.
            if end and week_start - timedelta(days=7) <= end <= week_end:
                adj.gentle = True
                adj.notes.append("First week back after a medical pause: lighter sessions.")
        elif kind == "other":
            details = change.get("details") or {}
            for day in details.get("days_off") or []:
                adj.days_off.add(date.fromisoformat(day))
            for short in details.get("shorter") or []:
                adj.minutes[date.fromisoformat(short["day"])] = int(short["minutes"])
            adj.avoid_muscles |= set(details.get("avoid_muscles") or [])
            if details.get("easier"):
                adj.gentle = True
            if details.get("summary"):
                adj.notes.append(details["summary"])
    return adj


# --- Last time, block and kept days ----------------------------------------------------


def history_from_logs(rows: list[dict[str, Any]]) -> dict[str, overload.LastTime]:
    """The most recent logged session of each exercise (rows newest first)."""
    latest_item: dict[str, str] = {}
    sets: dict[str, list[tuple[int | None, float | None]]] = {}
    info: dict[str, dict[str, Any]] = {}
    for row in rows:
        exercise_id = row["exercise_id"]
        item_id = row["session_item_id"]
        if latest_item.setdefault(exercise_id, item_id) != item_id:
            continue
        load = row.get("load_kg")
        sets.setdefault(exercise_id, []).append(
            (row.get("reps"), float(load) if load is not None else None)
        )
        info[exercise_id] = row.get("session_items") or {}
    history = {}
    for exercise_id, logged in sets.items():
        item = info[exercise_id]
        completion = (item.get("workout_sessions") or {}).get("session_completions")
        if isinstance(completion, list):
            completion = completion[0] if completion else None
        effort = (completion or {}).get("effort")
        history[exercise_id] = overload.LastTime(
            sets=logged,
            reps_min=item.get("reps_min"),
            reps_max=item.get("reps_max"),
            effort=effort,
        )
    return history


def block_from_plan(
    plan: dict[str, Any] | None, core: set[str]
) -> tuple[date | None, dict[str, list[str]]]:
    """A plan's block start, and its non-core main exercises by session focus."""
    if not plan:
        return None, {}
    by_focus: dict[str, list[str]] = {}
    for session in sorted(plan.get("workout_sessions") or [], key=lambda s: s["day"]):
        mains = sorted(
            (i for i in session.get("session_items") or [] if i["phase"] == "main"),
            key=lambda i: i["position"],
        )
        for item in mains:
            if item["exercise_id"] not in core:
                by_focus.setdefault(session["focus"], []).append(item["exercise_id"])
    start = plan.get("block_start")
    return (date.fromisoformat(start) if start else None), by_focus


PLAN_WITH_ITEMS = (
    "id,week_start,block_start,workout_sessions(id,day,title,focus,minutes,explanation,"
    f"session_items(id,{ITEM_FIELDS}),session_completions(id))"
)


async def load_inputs(
    select: Select,
    profile_id: str,
    week_start: date,
    today: date,
    reason: str = "new_week",
    changes: list[dict[str, Any]] | None = None,
) -> PlanInputs:
    """Everything a plan needs. `reason`: new_week (continue the block from last
    week), change (keep this week's block and picks), requested (start a new block).
    `changes`: extra (pending) changes to apply on top of those already applied."""
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
                "select": "equipment,available_days,minutes_per_session,location,experience,"
                "core_exercises",
                "profile_id": f"eq.{profile_id}",
            },
        )
    )[0]
    library = await select("exercises", {"select": LIBRARY_COLUMNS, "limit": "2000"})
    core = training.get("core_exercises") or []

    # The 6-week block: carry on from the plan before (new week) or this week's
    # plan (a change); "Make a new plan" starts a new block.
    block_start, block_main = None, {}
    if reason in ("new_week", "change"):
        params = {
            "select": PLAN_WITH_ITEMS,
            "profile_id": f"eq.{profile_id}",
            "status": "eq.active",
            "order": "week_start.desc",
            "limit": "1",
        }
        if reason == "new_week":
            params["week_start"] = f"lt.{week_start.isoformat()}"
        else:
            params["week_start"] = f"eq.{week_start.isoformat()}"
        previous = await select("workout_plans", params)
        start, by_focus = block_from_plan(previous[0] if previous else None, set(core))
        if start and week_start < start + timedelta(weeks=BLOCK_WEEKS):
            block_start, block_main = start, by_focus

    week_end = week_start + timedelta(days=6)
    applied = await select(
        "plan_changes",
        {
            "select": "kind,start_date,end_date,minutes,vacation_mode,cheat_mode,details",
            "profile_id": f"eq.{profile_id}",
            "status": "eq.applied",
            "start_date": f"lte.{week_end.isoformat()}",
            "or": f"(end_date.is.null,end_date.gte.{(week_start - timedelta(days=7)).isoformat()})",
        },
    )
    since = (today - timedelta(weeks=HISTORY_WEEKS)).isoformat()
    logs = await select(
        "exercise_logs",
        {
            "select": "exercise_id,session_item_id,reps,load_kg,"
            "session_items(reps_min,reps_max,workout_sessions(session_completions(effort)))",
            "profile_id": f"eq.{profile_id}",
            "logged_at": f"gte.{since}",
            "order": "logged_at.desc,set_number",
            "limit": "3000",
        },
    )
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
        core_exercises=core,
        adjustments=adjustments(applied + (changes or []), week_start, today),
        block_main=block_main,
        block_start=block_start,
        history=history_from_logs(logs),
    )


async def kept_sessions(
    select: Select, profile_id: str, week_start: date, today: date
) -> list[dict[str, Any]]:
    """Sessions from this week's current plan that a new plan keeps as they are:
    days before today, and today if it's been started (sets logged or done)."""
    rows = await select(
        "workout_plans",
        {
            "select": PLAN_WITH_ITEMS,
            "profile_id": f"eq.{profile_id}",
            "week_start": f"eq.{week_start.isoformat()}",
            "status": "eq.active",
        },
    )
    if not rows:
        return []
    started_today: set[str] = set()
    today_sessions = [s for s in rows[0]["workout_sessions"] if s["day"] == today.isoformat()]
    if today_sessions:
        item_ids = [i["id"] for s in today_sessions for i in s.get("session_items") or []]
        if item_ids:
            logged = await select(
                "exercise_logs",
                {"select": "id", "session_item_id": f"in.({','.join(item_ids)})", "limit": "1"},
            )
            if logged:
                started_today = {s["id"] for s in today_sessions}
        started_today |= {s["id"] for s in today_sessions if s.get("session_completions")}
    kept = []
    for session in rows[0]["workout_sessions"]:
        if session["day"] < today.isoformat() or session["id"] in started_today:
            kept.append(
                {
                    "day": session["day"],
                    "title": session["title"],
                    "focus": session["focus"],
                    "minutes": session["minutes"],
                    "explanation": session.get("explanation"),
                    "items": [
                        {k: v for k, v in item.items() if k != "id"}
                        for item in session.get("session_items") or []
                    ],
                }
            )
    return kept


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


def merge_kept(kept: list[dict[str, Any]], plan: dict[str, Any]) -> dict[str, Any]:
    """A new plan for the rest of the week, with the kept days in front."""
    kept_days = {s["day"] for s in kept}
    sessions = kept + [s for s in plan["sessions"] if s["day"] not in kept_days]
    return {**plan, "sessions": sorted(sessions, key=lambda s: s["day"])}
