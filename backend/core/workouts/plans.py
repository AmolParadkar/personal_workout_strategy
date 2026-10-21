"""Weekly plans: reading a week, making a plan (Vercel first, then the Mac
worker), applying or discarding a draft, and swapping exercises.
Spec: context/pages/workout-plan.md; flow: context/architecture.md
("Regenerating a plan")."""

import asyncio
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

import httpx2

from core.jobs import queue
from core.llm import LlmConfig, LlmError
from core.models.exercises import ExerciseSummary
from core.models.workouts import (
    PHASE_ORDER,
    MuscleSets,
    Plan,
    PlanChange,
    PlanItem,
    PlanSession,
    WeekPlan,
)
from core.supabase import SupabaseClient
from core.workouts import rules
from core.workouts.generate import build_plan
from core.workouts.inputs import (
    kept_sessions,
    load_inputs,
    merge_kept,
    status_to_save,
    user_select,
)

PLAN_JOB = "generate_workout_plan"
# Leave time inside Vercel's limit to save the plan or queue the job.
VERCEL_BUDGET_SECONDS = 25.0


class PlanNotFoundError(Exception):
    pass


class NotAnAlternativeError(Exception):
    """The chosen exercise isn't one of the offered swaps."""


# --- Reading a week -----------------------------------------------------------------

PLAN_SELECT = (
    "id,week_start,block_start,status,rationale,made_by,reason,created_at,"
    "workout_sessions(id,day,title,focus,minutes,explanation,"
    "session_items(id,phase,position,exercise_id,sets,reps_min,reps_max,duration_seconds,"
    "rest_seconds,target_load_kg,notes,exercises(name,images,primary_muscles,secondary_muscles)))"
)


def coverage(sessions: list[dict[str, Any]]) -> list[MuscleSets]:
    """Working sets per muscle for the week: main and activation work only."""
    totals: dict[str, float] = defaultdict(float)
    for session in sessions:
        for item in session.get("session_items") or []:
            if item["phase"] not in ("main", "activation"):
                continue
            sets = item.get("sets") or 1
            exercise = item.get("exercises") or {}
            for muscle in exercise.get("primary_muscles") or []:
                totals[muscle] += sets
            for muscle in exercise.get("secondary_muscles") or []:
                totals[muscle] += sets / 2
    return [
        MuscleSets(muscle=m, sets=round(s, 1))
        for m, s in sorted(totals.items(), key=lambda pair: -pair[1])
    ]


def to_plan(row: dict[str, Any]) -> Plan:
    sessions = sorted(row.get("workout_sessions") or [], key=lambda s: s["day"])
    return Plan(
        id=row["id"],
        week_start=row["week_start"],
        block_start=row.get("block_start"),
        status=row["status"],
        rationale=row.get("rationale"),
        made_by=row.get("made_by"),
        reason=row.get("reason"),
        created_at=row["created_at"],
        coverage=coverage(sessions),
        sessions=[
            PlanSession(
                id=s["id"],
                day=s["day"],
                title=s["title"],
                focus=s["focus"],
                minutes=s["minutes"],
                explanation=s.get("explanation"),
                items=[
                    PlanItem(
                        **{k: i.get(k) for k in PlanItem.model_fields if k in i},
                        exercise_name=(i.get("exercises") or {}).get("name") or i["exercise_id"],
                        image=((i.get("exercises") or {}).get("images") or [None])[0],
                        primary_muscles=(i.get("exercises") or {}).get("primary_muscles") or [],
                    )
                    for i in sorted(
                        s.get("session_items") or [],
                        key=lambda i: (PHASE_ORDER.index(i["phase"]), i["position"]),
                    )
                ],
            )
            for s in sessions
        ],
    )


async def _generating(
    supabase: SupabaseClient, token: str, profile_id: str, week_start: date
) -> bool:
    rows = await supabase.select(
        "jobs",
        {
            "select": "id",
            "type": f"eq.{PLAN_JOB}",
            "status": "in.(pending,processing)",
            "payload->>profile_id": f"eq.{profile_id}",
            "payload->>week_start": f"eq.{week_start.isoformat()}",
        },
        token,
    )
    return bool(rows)


async def get_week(
    supabase: SupabaseClient, token: str, profile_id: str, week_start: date, can_edit: bool
) -> WeekPlan:
    rows = await supabase.select(
        "workout_plans",
        {
            "select": PLAN_SELECT,
            "profile_id": f"eq.{profile_id}",
            "week_start": f"eq.{week_start.isoformat()}",
            "status": "in.(active,draft)",
        },
        token,
    )
    by_status = {row["status"]: to_plan(row) for row in rows}
    return WeekPlan(
        week_start=week_start,
        active=by_status.get("active"),
        draft=by_status.get("draft") if can_edit else None,
        generating=await _generating(supabase, token, profile_id, week_start),
        can_edit=can_edit,
        changes=await week_changes(supabase, token, profile_id, week_start, can_edit),
    )


CHANGE_LABELS = {
    "day_off": "Day off",
    "add_session": "Extra session",
    "shorter": "Shorter session",
    "vacation": "Vacation",
    "cheat_meal": "Cheat meal",
    "medical": "Medical pause",
    "other": "Change",
}


def change_summary(row: dict[str, Any]) -> str:
    def short(d: str) -> str:
        return date.fromisoformat(d).strftime("%a %d %b")

    start, end = row["start_date"], row.get("end_date")
    when = short(start) if not end or end == start else f"{short(start)} – {short(end)}"
    extra = {
        "shorter": f" ({row.get('minutes')} min)",
        "vacation": " (training while away)"
        if row.get("vacation_mode") == "travel"
        else " (no training)",
        "cheat_meal": " (extra load spread over the week)"
        if row.get("cheat_mode") == "spread"
        else " (workouts as planned)",
        "medical": "" if end else " (until you're back)",
        "other": f": {row.get('note')}" if row.get("note") else "",
    }.get(row["kind"], "")
    return f"{CHANGE_LABELS[row['kind']]} {when}{extra}"


async def week_changes(
    supabase: SupabaseClient, token: str, profile_id: str, week_start: date, can_edit: bool
) -> list[PlanChange]:
    """Changes affecting this week (applied, plus a pending one being previewed),
    and any medical pause still running."""
    week_end = week_start + timedelta(days=6)
    rows = await supabase.select(
        "plan_changes",
        {
            "select": "id,kind,start_date,end_date,minutes,vacation_mode,cheat_mode,note,status",
            "profile_id": f"eq.{profile_id}",
            "status": "in.(applied,pending)" if can_edit else "eq.applied",
            "start_date": f"lte.{week_end.isoformat()}",
            "or": f"(end_date.is.null,end_date.gte.{week_start.isoformat()})",
            "order": "start_date",
        },
        token,
    )
    return [
        PlanChange(
            id=row["id"],
            kind=row["kind"],
            start_date=row["start_date"],
            end_date=row.get("end_date"),
            status=row["status"],
            summary=change_summary(row),
            can_end=can_edit and row["kind"] == "medical" and not row.get("end_date"),
        )
        for row in rows
    ]


# --- Making a plan --------------------------------------------------------------------


async def generate(
    supabase: SupabaseClient,
    http: httpx2.AsyncClient,
    llm: LlmConfig | None,
    token: str,
    profile_id: str,
    today: date,
    reason: str,
    budget_seconds: float = VERCEL_BUDGET_SECONDS,
) -> WeekPlan:
    """Make this week's plan. It becomes active if the week has none, otherwise a
    draft to preview. Tried straight away with Groq; if that's slow or fails, the
    Mac worker makes it (Groq, then Ollama, then rules)."""
    week_start = rules.week_start_of(today)
    week = await get_week(supabase, token, profile_id, week_start, can_edit=True)
    if week.generating or (reason == "new_week" and (week.active or week.draft)):
        return week
    status = "draft" if week.active else "active"
    try:
        if llm is None or not llm.groq_api_key:
            raise LlmError("No cloud LLM on the API")
        select = user_select(supabase, token)
        inputs = await load_inputs(select, profile_id, week_start, today, reason)
        plan = await asyncio.wait_for(
            build_plan(inputs, http, llm, reason, rules_only_if_llm_fails=False),
            budget_seconds,
        )
        # Days already done this week stay as they were.
        plan = merge_kept(await kept_sessions(select, profile_id, week_start, today), plan)
        final = await status_to_save(
            user_select(supabase, token), profile_id, week_start, status, reason
        )
        if final:
            await supabase.rpc(
                "save_workout_plan",
                {
                    "p_profile_id": profile_id,
                    "p_week_start": week_start.isoformat(),
                    "p_status": final,
                    "p_plan": plan,
                },
                token,
            )
    except (LlmError, TimeoutError, httpx2.HTTPError):
        await queue.enqueue(
            supabase,
            token,
            profile_id,
            PLAN_JOB,
            {
                "profile_id": profile_id,
                "week_start": week_start.isoformat(),
                "today": today.isoformat(),
                "status": status,
                "reason": reason,
            },
        )
    return await get_week(supabase, token, profile_id, week_start, can_edit=True)


async def apply_draft(supabase: SupabaseClient, token: str, plan_id: str) -> None:
    try:
        await supabase.rpc("apply_workout_plan", {"p_plan_id": plan_id}, token)
    except httpx2.HTTPStatusError as error:
        raise PlanNotFoundError from error


async def discard_draft(
    supabase: SupabaseClient, token: str, profile_id: str, plan_id: str
) -> None:
    # A change previewed with this draft is dropped with it.
    await supabase.update(
        "plan_changes",
        {
            "draft_plan_id": f"eq.{plan_id}",
            "status": "eq.pending",
            "profile_id": f"eq.{profile_id}",
        },
        {"status": "discarded"},
        token,
        returning="id",
    )
    await supabase.delete(
        "workout_plans",
        {"id": f"eq.{plan_id}", "profile_id": f"eq.{profile_id}", "status": "eq.draft"},
        token,
    )


# --- Swapping an exercise ---------------------------------------------------------------

SWAP_COUNT = 6


async def _item(supabase: SupabaseClient, token: str, profile_id: str, item_id: str) -> dict:
    rows = await supabase.select(
        "session_items",
        {
            "select": "id,phase,exercise_id,session_id,"
            "exercises(primary_muscles,mechanic),workout_sessions(day,session_items(exercise_id))",
            "id": f"eq.{item_id}",
            "profile_id": f"eq.{profile_id}",
        },
        token,
    )
    if not rows:
        raise PlanNotFoundError
    return rows[0]


async def alternatives(
    supabase: SupabaseClient, token: str, profile_id: str, item_id: str
) -> list[ExerciseSummary]:
    """Exercises for the same phase that hit the same muscles with the person's
    equipment and level, not already in that session."""
    item = await _item(supabase, token, profile_id, item_id)
    day = date.fromisoformat(item["workout_sessions"]["day"])
    inputs = await load_inputs(
        user_select(supabase, token), profile_id, rules.week_start_of(day), day
    )
    kit = rules.kit_for(inputs.equipment, inputs.location)
    pools = rules.phase_pools(rules.usable_library(inputs.library, kit, inputs.experience), kit)
    muscles = (item.get("exercises") or {}).get("primary_muscles") or []
    in_session = {i["exercise_id"] for i in item["workout_sessions"]["session_items"]}
    mechanic = (item.get("exercises") or {}).get("mechanic")
    pool = [
        e
        for e in pools[item["phase"]]
        if e["id"] not in in_session and set(e.get("primary_muscles") or []) & set(muscles)
    ]
    # Same kind of movement first (compound for compound), then the best muscle match.
    pool.sort(
        key=lambda e: (
            e.get("mechanic") != mechanic,
            -len(set(e.get("primary_muscles") or []) & set(muscles)),
            e["name"],
        )
    )
    return [
        ExerciseSummary(
            id=e["id"],
            name=e["name"],
            category=e.get("category"),
            equipment=e.get("equipment"),
            level=e.get("level"),
            primary_muscles=e.get("primary_muscles") or [],
            image=None,
        )
        for e in pool[:SWAP_COUNT]
    ]


async def swap(
    supabase: SupabaseClient, token: str, profile_id: str, item_id: str, exercise_id: str
) -> None:
    offered = await alternatives(supabase, token, profile_id, item_id)
    if exercise_id not in {e.id for e in offered}:
        raise NotAnAlternativeError
    await supabase.update(
        "session_items",
        {"id": f"eq.{item_id}", "profile_id": f"eq.{profile_id}"},
        {"exercise_id": exercise_id},
        token,
        returning="id",
    )


# --- Choosing core lifts -----------------------------------------------------------------

CORE_OPTIONS = 20


async def core_lift_options(
    supabase: SupabaseClient, token: str, profile_id: str, today: date, search: str | None
) -> list[ExerciseSummary]:
    """Big compound lifts this person can do with their equipment and level,
    matching `search` (every word, any order)."""
    inputs = await load_inputs(
        user_select(supabase, token), profile_id, rules.week_start_of(today), today, "requested"
    )
    kit = rules.kit_for(inputs.equipment, inputs.location)
    pool = rules.phase_pools(rules.usable_library(inputs.library, kit, inputs.experience), kit)
    words = [w.lower() for w in (search or "").split() if w]
    options = [
        e
        for e in pool["main"]
        if e.get("mechanic") == "compound" and all(w in e["name"].lower() for w in words)
    ]
    options.sort(key=lambda e: (len(e["name"]), e["name"]))
    return [
        ExerciseSummary(
            id=e["id"],
            name=e["name"],
            category=e.get("category"),
            equipment=e.get("equipment"),
            level=e.get("level"),
            primary_muscles=e.get("primary_muscles") or [],
            image=None,
        )
        for e in options[:CORE_OPTIONS]
    ]
