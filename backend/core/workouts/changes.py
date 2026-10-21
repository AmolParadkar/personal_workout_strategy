"""Changing this week's plan (context/pages/workout-plan.md, "Changes"): a day
off, an extra or shorter session, vacation, a cheat meal, a medical pause, or
something else in the person's own words. Each makes a preview (draft) that's
applied only when confirmed; applied changes keep shaping later plans."""

from datetime import date, timedelta
from typing import Any

import httpx2
from pydantic import BaseModel, Field

from core.llm import LlmConfig, LlmError, ask_json
from core.models.workouts import PlanChangeRequest, WeekPlan
from core.supabase import SupabaseClient
from core.workouts import rules
from core.workouts.generate import build_plan
from core.workouts.inputs import kept_sessions, load_inputs, merge_kept, user_select
from core.workouts.plans import get_week

MAX_AHEAD = timedelta(days=90)
MUSCLES = {
    "abdominals",
    "abductors",
    "adductors",
    "biceps",
    "calves",
    "chest",
    "forearms",
    "glutes",
    "hamstrings",
    "lats",
    "lower back",
    "middle back",
    "neck",
    "quadriceps",
    "shoulders",
    "traps",
    "triceps",
}


class ChangeError(Exception):
    """The change doesn't make sense (shown to the person as is)."""


class NotUnderstoodError(Exception):
    """'Something else' couldn't be turned into a change."""


class Shorter(BaseModel):
    day: date
    minutes: int = Field(ge=10, le=300)


class OtherChange(BaseModel):
    days_off: list[date] = Field(default_factory=list)
    shorter: list[Shorter] = Field(default_factory=list)
    avoid_muscles: list[str] = Field(default_factory=list)
    easier: bool = False
    summary: str = Field(min_length=3, max_length=200)


def check_request(body: PlanChangeRequest, training_days: set[date]) -> PlanChangeRequest:
    """Fill in and check each kind's details. Dates are local and from today on."""
    today = body.today
    week_end = rules.week_start_of(today) + timedelta(days=6)
    start, end = body.start_date, body.end_date
    if start < today:
        raise ChangeError("Choose today or a later day.")
    if start > today + MAX_AHEAD or (end and end > today + MAX_AHEAD):
        raise ChangeError("Changes can be up to 90 days ahead.")
    if end and end < start:
        raise ChangeError("The end date is before the start date.")
    kind = body.kind
    if kind in ("day_off", "add_session", "shorter") and start > week_end:
        raise ChangeError("This change is for this week's plan: choose a day this week.")
    if kind == "add_session" and start in training_days:
        raise ChangeError("That day already has a session.")
    if kind == "shorter":
        if not body.minutes:
            raise ChangeError("How many minutes that day?")
        if start not in training_days:
            raise ChangeError("That day has no session to shorten.")
    if kind == "vacation" and not (end and body.vacation_mode):
        raise ChangeError("Choose the dates and whether you'll train while away.")
    if kind == "cheat_meal" and not body.cheat_mode:
        raise ChangeError("Spread the extra load across the week, or keep the workouts as planned?")
    if kind == "other" and not (body.note and body.note.strip()):
        raise ChangeError("Describe the change.")
    if kind in ("day_off", "add_session", "shorter", "cheat_meal"):
        end = start if kind != "day_off" else (end or start)
    return body.model_copy(update={"end_date": end})


async def interpret(
    http: httpx2.AsyncClient,
    llm: LlmConfig,
    note: str,
    today: date,
    sessions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Turn "something else" into days off, shorter days, muscles to avoid or an
    easier week, for the rest of this week."""
    week_end = rules.week_start_of(today) + timedelta(days=6)
    plan = (
        "\n".join(f"- {s['day']}: {s['title']} ({s['minutes']} min)" for s in sessions) or "- none"
    )
    day_name = today.strftime("%A")
    prompt = f"""Someone wants to change this week's workout plan.
Today is {today.isoformat()} ({day_name}).

Remaining sessions:
{plan}

What they said: "{note.strip()}"

Turn it into changes for days from {today.isoformat()} to {week_end.isoformat()} only:
- "days_off": dates with no training
- "shorter": [{{"day": "YYYY-MM-DD", "minutes": N}}] for shorter sessions
- "avoid_muscles": muscles to keep out of the plan, from: {", ".join(sorted(MUSCLES))}
- "easier": true for a lighter week (fewer sets, lower weights)
- "summary": one short sentence describing the change
Use empty lists or false when something doesn't apply. Return JSON with exactly those keys."""
    try:
        answer = await ask_json(
            http,
            llm,
            "You turn requests into structured workout plan changes. Answer with JSON only.",
            prompt,
            OtherChange,
            300,
        )
    except LlmError as error:
        raise NotUnderstoodError from error
    value = answer.value
    in_week = lambda d: today <= d <= week_end  # noqa: E731
    details = {
        "days_off": [d.isoformat() for d in value.days_off if in_week(d)],
        "shorter": [
            {"day": s.day.isoformat(), "minutes": s.minutes}
            for s in value.shorter
            if in_week(s.day)
        ],
        "avoid_muscles": [m for m in value.avoid_muscles if m in MUSCLES],
        "easier": value.easier,
        "summary": value.summary,
    }
    if not (
        details["days_off"] or details["shorter"] or details["avoid_muscles"] or details["easier"]
    ):
        raise NotUnderstoodError
    return details


async def request_change(
    supabase: SupabaseClient,
    http: httpx2.AsyncClient,
    llm: LlmConfig | None,
    token: str,
    profile_id: str,
    body: PlanChangeRequest,
) -> WeekPlan:
    """Save the change and make a preview of this week with it. A change that only
    affects later weeks is applied straight away (nothing to preview yet)."""
    today = body.today
    week_start = rules.week_start_of(today)
    week_end = week_start + timedelta(days=6)
    week = await get_week(supabase, token, profile_id, week_start, can_edit=True)
    sessions = week.active.sessions if week.active else []
    training_days = {s.day for s in sessions}
    body = check_request(body, training_days)

    details = None
    if body.kind == "other":
        if llm is None or not llm.groq_api_key:
            raise NotUnderstoodError
        remaining = [
            {"day": s.day.isoformat(), "title": s.title, "minutes": s.minutes}
            for s in sessions
            if s.day >= today
        ]
        details = await interpret(http, llm, body.note or "", today, remaining)

    this_week = body.start_date <= week_end
    rows = await supabase.insert(
        "plan_changes",
        {
            "profile_id": profile_id,
            "kind": body.kind,
            "start_date": body.start_date.isoformat(),
            "end_date": body.end_date.isoformat() if body.end_date else None,
            "minutes": body.minutes,
            "vacation_mode": body.vacation_mode,
            "cheat_mode": body.cheat_mode,
            "note": body.note.strip() if body.note else None,
            "details": details,
        },
        token,
        returning="id",
    )
    change_id = rows[0]["id"]
    if not this_week or (body.kind == "cheat_meal" and body.cheat_mode == "as_planned"):
        await supabase.update(
            "plan_changes", {"id": f"eq.{change_id}"}, {"status": "applied"}, token, returning="id"
        )
        week = await get_week(supabase, token, profile_id, week_start, can_edit=True)
        week.message = (
            "Saved. It will shape that week's plan when it's made."
            if not this_week
            else "Saved. Workouts stay as planned; it's noted for the Nutrition Plan."
        )
        return week

    pending = [
        {
            "kind": body.kind,
            "start_date": body.start_date.isoformat(),
            "end_date": body.end_date.isoformat() if body.end_date else None,
            "minutes": body.minutes,
            "vacation_mode": body.vacation_mode,
            "cheat_mode": body.cheat_mode,
            "details": details,
        }
    ]
    plan_id = await make_preview(supabase, http, llm, token, profile_id, today, pending)
    await supabase.update(
        "plan_changes", {"id": f"eq.{change_id}"}, {"draft_plan_id": plan_id}, token, returning="id"
    )
    return await get_week(supabase, token, profile_id, week_start, can_edit=True)


async def make_preview(
    supabase: SupabaseClient,
    http: httpx2.AsyncClient,
    llm: LlmConfig | None,
    token: str,
    profile_id: str,
    today: date,
    pending: list[dict[str, Any]],
) -> str:
    """A draft of the rest of this week with the changes, keeping days already
    done and this block's exercises (the LLM is only asked if a new kind of
    session appears; rules otherwise)."""
    week_start = rules.week_start_of(today)
    select = user_select(supabase, token)
    inputs = await load_inputs(select, profile_id, week_start, today, "change", pending)
    plan = await build_plan(inputs, http, llm, "change")
    plan = merge_kept(await kept_sessions(select, profile_id, week_start, today), plan)
    return await supabase.rpc(
        "save_workout_plan",
        {
            "p_profile_id": profile_id,
            "p_week_start": week_start.isoformat(),
            "p_status": "draft",
            "p_plan": plan,
        },
        token,
    )


async def end_medical(
    supabase: SupabaseClient,
    http: httpx2.AsyncClient,
    llm: LlmConfig | None,
    token: str,
    profile_id: str,
    change_id: str,
    today: date,
) -> WeekPlan:
    """ "I'm back": end the pause yesterday and preview the rest of the week, lighter."""
    rows = await supabase.select(
        "plan_changes",
        {
            "select": "id,start_date",
            "id": f"eq.{change_id}",
            "profile_id": f"eq.{profile_id}",
            "kind": "eq.medical",
            "end_date": "is.null",
        },
        token,
    )
    if not rows:
        raise ChangeError("No running medical pause of yours with that id.")
    start = date.fromisoformat(rows[0]["start_date"])
    end = max(start, today - timedelta(days=1))
    await supabase.update(
        "plan_changes",
        {"id": f"eq.{change_id}"},
        {"end_date": end.isoformat()},
        token,
        returning="id",
    )
    await make_preview(supabase, http, llm, token, profile_id, today, [])
    week = await get_week(supabase, token, profile_id, rules.week_start_of(today), can_edit=True)
    week.message = "Welcome back. Here's the rest of the week, lighter to start with."
    return week
