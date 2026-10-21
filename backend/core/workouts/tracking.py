"""Doing the workout (context/pages/plan-for-today.md): today's session, logging
sets, finishing with an effort rating, and the workout streak."""

from datetime import date, timedelta
from typing import Any

from core.models.workouts import (
    CatchUp,
    Completion,
    LogSet,
    SetLog,
    TodayWorkout,
)
from core.supabase import SupabaseClient
from core.workouts import rules
from core.workouts.plans import PLAN_SELECT, to_plan

STREAK_WEEKS = 26
LOG_COLUMNS = "id,session_item_id,set_number,reps,load_kg,duration_seconds"


class NotYourSessionError(Exception):
    """No such session or item in the caller's own plan."""


def _one(embedded: Any) -> dict[str, Any] | None:
    """A one-to-one embed (a session has at most one completion) comes back as an
    object, or a list from some queries; either way, the row or None."""
    if isinstance(embedded, list):
        return embedded[0] if embedded else None
    return embedded or None


def streak(sessions: list[dict[str, Any]], today: date) -> int:
    """Planned workouts done in a row, newest first. A session this week that isn't
    done yet doesn't count but doesn't break the streak (it can still be done);
    an earlier week's undone session ends it."""
    this_week = rules.week_start_of(today)
    count = 0
    for session in sorted(sessions, key=lambda s: s["day"], reverse=True):
        day = date.fromisoformat(session["day"])
        if day > today:
            continue
        if _one(session.get("session_completions")):
            count += 1
        elif day < this_week:
            break
    return count


async def _streak(supabase: SupabaseClient, token: str, profile_id: str, today: date) -> int:
    since = rules.week_start_of(today) - timedelta(weeks=STREAK_WEEKS)
    rows = await supabase.select(
        "workout_sessions",
        {
            "select": "day,session_completions(id),workout_plans!inner(status)",
            "profile_id": f"eq.{profile_id}",
            "workout_plans.status": "eq.active",
            "day": f"gte.{since.isoformat()}",
        },
        token,
    )
    return streak(rows, today)


async def get_today(
    supabase: SupabaseClient,
    token: str,
    profile_id: str,
    day: date,
    can_edit: bool,
    session_id: str | None = None,
) -> TodayWorkout:
    """The workout for `day` (or an earlier undone one this week, by `session_id`)."""
    week_start = rules.week_start_of(day)
    rows = await supabase.select(
        "workout_plans",
        {
            "select": PLAN_SELECT.replace(
                "workout_sessions(id,", "workout_sessions(id,session_completions(done_on,effort),"
            ),
            "profile_id": f"eq.{profile_id}",
            "week_start": f"eq.{week_start.isoformat()}",
            "status": "eq.active",
        },
        token,
    )
    streak_count = await _streak(supabase, token, profile_id, day)
    if not rows:
        return TodayWorkout(
            day=day,
            has_plan=False,
            session=None,
            logs=[],
            completion=None,
            catch_up=[],
            streak=streak_count,
            can_edit=can_edit,
        )
    raw_sessions = rows[0].get("workout_sessions") or []
    plan = to_plan(rows[0])
    done = {s["id"]: _one(s.get("session_completions")) for s in raw_sessions}
    chosen = next(
        (s for s in plan.sessions if (s.id == session_id if session_id else s.day == day)),
        None,
    )
    catch_up = [
        CatchUp(session_id=s.id, day=s.day, title=s.title)
        for s in plan.sessions
        if s.day < day and not done.get(s.id)
    ]
    logs: list[SetLog] = []
    completion = None
    if chosen:
        item_ids = [i.id for i in chosen.items]
        if item_ids:
            log_rows = await supabase.select(
                "exercise_logs",
                {
                    "select": LOG_COLUMNS,
                    "session_item_id": f"in.({','.join(item_ids)})",
                    "order": "set_number",
                },
                token,
            )
            logs = [SetLog(**row) for row in log_rows]
        if done.get(chosen.id):
            completion = Completion(**done[chosen.id])
    return TodayWorkout(
        day=day,
        has_plan=True,
        session=chosen,
        logs=logs,
        completion=completion,
        catch_up=catch_up,
        streak=streak_count,
        can_edit=can_edit,
    )


async def _own_item(supabase: SupabaseClient, token: str, profile_id: str, item_id: str) -> dict:
    rows = await supabase.select(
        "session_items",
        {"select": "id,exercise_id", "id": f"eq.{item_id}", "profile_id": f"eq.{profile_id}"},
        token,
    )
    if not rows:
        raise NotYourSessionError
    return rows[0]


async def log_set(supabase: SupabaseClient, token: str, profile_id: str, body: LogSet) -> SetLog:
    """Save one set (logging the same set again corrects it)."""
    item = await _own_item(supabase, token, profile_id, body.session_item_id)
    values = {"reps": body.reps, "load_kg": body.load_kg, "duration_seconds": body.duration_seconds}
    filters = {
        "session_item_id": f"eq.{body.session_item_id}",
        "set_number": f"eq.{body.set_number}",
        "profile_id": f"eq.{profile_id}",
    }
    updated = await supabase.update("exercise_logs", filters, values, token, returning=LOG_COLUMNS)
    if updated:
        return SetLog(**updated[0])
    rows = await supabase.insert(
        "exercise_logs",
        {
            "profile_id": profile_id,
            "session_item_id": body.session_item_id,
            "exercise_id": item["exercise_id"],
            "set_number": body.set_number,
            **values,
        },
        token,
        returning=LOG_COLUMNS,
    )
    return SetLog(**rows[0])


async def delete_set(supabase: SupabaseClient, token: str, profile_id: str, log_id: str) -> None:
    await supabase.delete(
        "exercise_logs", {"id": f"eq.{log_id}", "profile_id": f"eq.{profile_id}"}, token
    )


async def _own_session(
    supabase: SupabaseClient, token: str, profile_id: str, session_id: str
) -> None:
    rows = await supabase.select(
        "workout_sessions",
        {"select": "id", "id": f"eq.{session_id}", "profile_id": f"eq.{profile_id}"},
        token,
    )
    if not rows:
        raise NotYourSessionError


async def complete(
    supabase: SupabaseClient,
    token: str,
    profile_id: str,
    session_id: str,
    done_on: date,
    effort: str | None,
) -> None:
    """Mark a session done (and rate how hard it was); again just updates the rating."""
    await _own_session(supabase, token, profile_id, session_id)
    updated = await supabase.update(
        "session_completions",
        {"session_id": f"eq.{session_id}", "profile_id": f"eq.{profile_id}"},
        {"effort": effort},
        token,
        returning="id",
    )
    if not updated:
        await supabase.insert(
            "session_completions",
            {
                "profile_id": profile_id,
                "session_id": session_id,
                "done_on": done_on.isoformat(),
                "effort": effort,
            },
            token,
            returning="id",
        )


async def undo_complete(
    supabase: SupabaseClient, token: str, profile_id: str, session_id: str
) -> None:
    await supabase.delete(
        "session_completions",
        {"session_id": f"eq.{session_id}", "profile_id": f"eq.{profile_id}"},
        token,
    )
