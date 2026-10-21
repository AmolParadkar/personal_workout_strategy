"""Making a weekly workout plan (context/pages/workout-plan.md).

1. Rules (core/workouts/rules.py) set the shape: training days from today on
   (with any changes: days off, extra days, shorter days, travel days), the split,
   phase minutes, and the warm-up, activation and cool-down exercises.
2. Core lifts (chosen in Settings) go into the sessions that train their muscles,
   every week, so their loads can keep going up.
3. Other main exercises stay the same for a 6-week block: within a block they're
   reused from last week's plan; at the start of a block (or "Make a new plan")
   the LLM picks them from a short pre-filtered list, sets sets/reps/rest for the
   person's goals, experience and injuries, and explains the sessions. Its answer
   is checked; anything that doesn't fit is replaced by the rules' choice.
4. Progressive overload sets each main exercise's target from what was actually
   lifted last time (core/workouts/overload.py).
5. Without a usable LLM answer, the rules make the whole plan.

The result is the JSON that public.save_workout_plan stores.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import httpx2
from pydantic import BaseModel, Field

from core.llm import LlmConfig, LlmError, ask_json
from core.workouts import overload, rules

SYSTEM = (
    "You are an experienced strength and conditioning coach planning a week of "
    "workouts for one adult. Choose safe, effective exercises, respect injuries and "
    "limitations, and follow current evidence-based guidance. Answer with JSON only."
)
BLOCK_WEEKS = 6
# A cheat meal's extra load, spread as cardio over the following sessions.
CHEAT_SPREAD_MINUTES = 30
CHEAT_SPREAD_MAX_PER_DAY = 10
# Each core lift goes into at most this many sessions a week.
CORE_SESSIONS_PER_WEEK = 2


@dataclass
class Adjustments:
    """Changes in effect this week (from plan_changes), already turned into days."""

    days_off: set[date] = field(default_factory=set)
    extra_days: set[date] = field(default_factory=set)
    minutes: dict[date, int] = field(default_factory=dict)
    # Training while away: bodyweight and bands only.
    travel_days: set[date] = field(default_factory=set)
    # Extra cardio minutes per day (a cheat meal's load spread across the week).
    extra_cardio: dict[date, int] = field(default_factory=dict)
    # Cheat meals with their extra load spread over the following sessions.
    spread_after: list[date] = field(default_factory=list)
    avoid_muscles: set[str] = field(default_factory=set)
    # Lighter week: back from a medical pause, or asked for in "something else".
    gentle: bool = False
    notes: list[str] = field(default_factory=list)


@dataclass
class PlanInputs:
    profile_id: str
    week_start: date
    today: date
    goals: list[str]
    experience: str
    available_days: list[str]
    minutes_per_session: int
    equipment: list[str]
    location: str | None
    sex: str | None
    age: int | None
    injuries: str | None
    library: list[dict[str, Any]]
    core_exercises: list[str] = field(default_factory=list)
    adjustments: Adjustments = field(default_factory=Adjustments)
    # Main (non-core) exercises by session focus from last week, if still in the
    # same 6-week block; and when that block started.
    block_main: dict[str, list[str]] = field(default_factory=dict)
    block_start: date | None = None
    # What was lifted last time, by exercise (for progressive overload).
    history: dict[str, overload.LastTime] = field(default_factory=dict)

    def library_by_id(self) -> dict[str, dict[str, Any]]:
        if not hasattr(self, "_by_id"):
            self._by_id = {e["id"]: e for e in self.library}
        return self._by_id


class LlmSession(BaseModel):
    day: date
    title: str = Field(min_length=3, max_length=80)
    explanation: str = Field(min_length=10, max_length=400)
    # Compact, to fit Groq's free output limit:
    # [exercise_id, sets, reps_min, reps_max, rest_seconds]. Objects with those keys
    # are accepted too, in case the LLM answers that way.
    main: list[list[str | int] | dict[str, Any]] = Field(default_factory=list, max_length=8)


class LlmWeek(BaseModel):
    rationale: str = Field(min_length=10, max_length=800)
    sessions: list[LlmSession]


# Groq's free tier allows 1,000 output tokens a minute for Qwen; stay under it.
MAX_ANSWER_TOKENS = 950


@dataclass
class Skeleton:
    day: date
    focus: str
    muscles: list[str]
    minutes: rules.PhaseMinutes
    total_minutes: int
    # Non-core main exercises to choose.
    main_count: int
    candidates: list[dict[str, Any]]
    warm_cool: list[dict[str, Any]]
    rules_main: list[dict[str, Any]]
    core: list[dict[str, Any]] = field(default_factory=list)
    # Non-core main exercises kept from last week (same 6-week block).
    reused: list[dict[str, Any]] = field(default_factory=list)
    travel: bool = False


def plan_days(inputs: PlanInputs) -> list[date]:
    """Training days this week from today on, with days off and extra days applied."""
    adj = inputs.adjustments
    base = rules.training_days(inputs.week_start, inputs.today, inputs.available_days)
    week_end = inputs.week_start + timedelta(days=6)
    extra = {d for d in adj.extra_days if inputs.today <= d <= week_end}
    days = sorted((set(base) | extra) - adj.days_off)
    return days[: rules.MAX_SESSIONS]


def spread_cardio(days: list[date], cheat_days: list[date]) -> dict[date, int]:
    """Extra cardio minutes per training day after each cheat meal (no single
    "burn it off" session: at most 10 extra minutes a day)."""
    extra: dict[date, int] = {}
    for cheat in cheat_days:
        after = [d for d in days if d > cheat] or [d for d in days if d >= cheat]
        if not after:
            continue
        each = min(CHEAT_SPREAD_MAX_PER_DAY, round(CHEAT_SPREAD_MINUTES / len(after)))
        for day in after:
            extra[day] = extra.get(day, 0) + each
    return extra


def block_week(inputs: PlanInputs) -> int:
    """Which week of the 6-week block this is (1 to 6)."""
    start = inputs.block_start or inputs.week_start
    return (inputs.week_start - start).days // 7 + 1


def assign_core(
    core: list[dict[str, Any]], sessions: list[tuple[date, str]]
) -> dict[date, list[dict[str, Any]]]:
    """Put each core lift into the (up to 2) sessions that best train its muscles,
    spaced apart; a lift that matches no session's focus goes into the closest one."""
    placed: dict[date, list[dict[str, Any]]] = {day: [] for day, _ in sessions}
    for exercise in core:
        primary = set(exercise.get("primary_muscles") or [])
        secondary = set(exercise.get("secondary_muscles") or [])
        scored = sorted(
            (
                (
                    2 * len(primary & set(rules.FOCUS_MUSCLES[focus]))
                    + len(secondary & set(rules.FOCUS_MUSCLES[focus])),
                    day,
                )
                for day, focus in sessions
            ),
            key=lambda pair: (-pair[0], pair[1]),
        )
        chosen: list[date] = []
        for score, day in scored:
            if score <= 0 and chosen:
                break
            if any(abs((day - other).days) < 2 for other in chosen):
                continue  # not on back-to-back days
            chosen.append(day)
            if len(chosen) == CORE_SESSIONS_PER_WEEK or score <= 0:
                break
        for day in chosen:
            placed[day].append(exercise)
    return placed


def skeleton(inputs: PlanInputs) -> list[Skeleton]:
    """Everything the rules decide, per training day."""
    adj = inputs.adjustments
    home_kit = rules.kit_for(inputs.equipment, inputs.location)
    travel_kit = rules.kit_for(["bodyweight", "resistance_bands"], "travel")

    def avoiding(exercises: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [e for e in exercises if not set(e.get("primary_muscles") or []) & adj.avoid_muscles]

    pools_by_kit = {}
    for name, kit in (("home", home_kit), ("travel", travel_kit)):
        library = rules.usable_library(inputs.library, kit, inputs.experience)
        pools = rules.phase_pools(library, kit)
        pools_by_kit[name] = {phase: avoiding(pool) for phase, pool in pools.items()}

    days = plan_days(inputs)
    focuses = rules.split_for(len(days))
    by_id = {e["id"]: e for e in inputs.library}
    home_usable = {e["id"] for e in pools_by_kit["home"]["main"]}
    core = [by_id[i] for i in inputs.core_exercises if i in by_id and i in home_usable]
    core_by_day = assign_core(core, list(zip(days, focuses, strict=True)))

    extra_by_day = dict(adj.extra_cardio)
    for day, minutes in spread_cardio(days, adj.spread_after).items():
        extra_by_day[day] = extra_by_day.get(day, 0) + minutes
    sessions: list[Skeleton] = []
    used_main: set[str] = set(inputs.core_exercises)
    reuse_queue = {focus: list(ids) for focus, ids in inputs.block_main.items()}
    for day, focus in zip(days, focuses, strict=True):
        travel = day in adj.travel_days
        pools = pools_by_kit["travel" if travel else "home"]
        rng = rules.rng_for(inputs.profile_id, inputs.week_start, day)
        muscles = [m for m in rules.FOCUS_MUSCLES[focus] if m not in adj.avoid_muscles]
        total = adj.minutes.get(day, inputs.minutes_per_session)
        minutes = rules.phase_minutes(total, inputs.goals)
        extra_cardio = extra_by_day.get(day, 0)
        if extra_cardio:
            minutes = rules.PhaseMinutes(
                minutes.cardio + extra_cardio,
                minutes.mobility,
                minutes.activation,
                minutes.main,
                minutes.cooldown,
            )
        count = rules.main_exercise_count(minutes.main)
        session_core = [] if travel else core_by_day.get(day, [])[:count]
        wanted = max(0, count - len(session_core))

        # Same block: keep last week's picks for this kind of session, if still doable.
        reused: list[dict[str, Any]] = []
        if not travel and focus in reuse_queue:
            usable = {e["id"]: e for e in pools["main"]}
            core_ids = set(inputs.core_exercises)
            for exercise_id in reuse_queue[focus]:
                # Copied as last week had them (repeats included), minus core lifts.
                if exercise_id in usable and exercise_id not in core_ids and len(reused) < wanted:
                    reused.append(usable[exercise_id])
            # The next session with this focus reuses the rest of the list.
            reuse_queue[focus] = reuse_queue[focus][len(reused) :]

        candidates = rules.main_candidates(
            pools, muscles or rules.FOCUS_MUSCLES[focus], rng, avoid=used_main
        )
        # Core lifts are placed above, never offered again as extra picks.
        candidates = [c for c in candidates if c["id"] not in set(inputs.core_exercises)]
        rules_main = candidates[:wanted]
        used_main |= {e["id"] for e in session_core + reused + rules_main}
        sessions.append(
            Skeleton(
                day=day,
                focus=focus,
                muscles=muscles or rules.FOCUS_MUSCLES[focus],
                minutes=minutes,
                total_minutes=total + extra_cardio,
                main_count=wanted,
                candidates=candidates,
                warm_cool=rules.warm_and_cool(
                    pools, muscles or rules.FOCUS_MUSCLES[focus], minutes, rng
                ),
                rules_main=rules_main,
                core=session_core,
                reused=reused if len(reused) == wanted else [],
                travel=travel,
            )
        )
    return sessions


def unusable_core(inputs: PlanInputs) -> list[str]:
    """Names of chosen core lifts this person can't do with their equipment and level."""
    kit = rules.kit_for(inputs.equipment, inputs.location)
    by_id = inputs.library_by_id()
    return [
        by_id[i]["name"]
        for i in inputs.core_exercises
        if i in by_id and not rules.usable(by_id[i], kit, inputs.experience)
    ]


def needs_llm(s: Skeleton) -> bool:
    return s.main_count > 0 and not s.reused


def build_prompt(inputs: PlanInputs, sessions: list[Skeleton]) -> str:
    def line(e: dict[str, Any]) -> str:
        muscles = ", ".join(e.get("primary_muscles") or [])
        return f"  - {e['id']}: {e['name']} ({muscles}; {e.get('equipment') or 'body only'})"

    blocks = []
    for s in sessions:
        if not needs_llm(s):
            continue
        core = (
            f" Already in it (core lifts): {', '.join(e['name'] for e in s.core)}."
            if s.core
            else ""
        )
        where = " Away from home: bodyweight and bands only." if s.travel else ""
        blocks.append(
            f"{s.day.isoformat()} ({s.day.strftime('%A')}): {rules.FOCUS_TITLES[s.focus]}, "
            f"{s.total_minutes} min ({s.minutes.main} min for the main workout).{core}{where} "
            f"Choose {s.main_count} more main exercises from:\n"
            + "\n".join(map(line, s.candidates))
        )
    about = ", ".join(
        part
        for part in (
            f"age {inputs.age}" if inputs.age else None,
            inputs.sex,
            f"experience: {inputs.experience}",
            f"goals: {', '.join(inputs.goals) or 'general health'}",
        )
        if part
    )
    injuries = inputs.injuries.strip() if inputs.injuries else "none given"
    notes = "\n".join(f"- {n}" for n in inputs.adjustments.notes) or "- none"
    return f"""Plan the main workout for these training days this week.

Person: {about}.
Injuries or limitations: {injuries}
This week:
{notes}

Warm-up (cardio, mobility, activation) and cool-down are already planned.
For each day, choose the main exercises ONLY from that day's list (use the ids),
best order first (big compound lifts first). Avoid anything unsafe for the injuries
above. Set sets, a rep range and rest (seconds) that suit the goals and experience.
Don't repeat an exercise on two days unless the list leaves no choice.

{chr(10).join(blocks)}

Keep it short. Return JSON:
{{"rationale": "one or two sentences on how the week fits the goals",
  "sessions": [{{"day": "YYYY-MM-DD", "title": "short name",
    "explanation": "one sentence: what it is and which muscles it targets",
    "main": [["exercise_id", sets, reps_min, reps_max, rest_seconds]]}}]}}"""


def _llm_main(s: Skeleton, answer: LlmSession | None) -> list[dict[str, Any]] | None:
    """The LLM's main exercises for a session, if they're valid; otherwise None."""
    if answer is None:
        return None
    allowed = {e["id"] for e in s.candidates}
    chosen = []
    keys = ("exercise_id", "sets", "reps_min", "reps_max", "rest_seconds")
    for raw in answer.main:
        entry = [raw.get(k) for k in keys] if isinstance(raw, dict) else raw
        if len(entry) != 5 or entry[0] not in allowed:
            continue
        try:
            sets, low, high, rest = (int(v) for v in entry[1:])
        except (TypeError, ValueError):
            continue
        if not (1 <= sets <= 6 and 1 <= low <= 30 and 1 <= high <= 30 and 15 <= rest <= 300):
            continue
        chosen.append((str(entry[0]), sets, min(low, high), max(low, high), rest))
    ids = [c[0] for c in chosen]
    minimum = 1 if s.core else 2
    if len(chosen) < min(minimum, s.main_count) or len(set(ids)) != len(ids):
        return None
    if len(chosen) > s.main_count + 1:
        return None
    return [
        {
            "phase": "main",
            "exercise_id": exercise_id,
            "sets": sets,
            "reps_min": low,
            "reps_max": high,
            "rest_seconds": rest,
        }
        for exercise_id, sets, low, high, rest in chosen
    ]


def rules_explanation(s: Skeleton) -> str:
    muscles = ", ".join(s.muscles[:5])
    away = " (travel version: bodyweight and bands)" if s.travel else ""
    return (
        f"{rules.FOCUS_TITLES[s.focus]} session{away}: warm up, then strength work for "
        f"{muscles}, then stretch the muscles you used."
    )


def _numbered(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**item, "position": position} for position, item in enumerate(items)]


def assemble(
    inputs: PlanInputs,
    sessions: list[Skeleton],
    answer: LlmWeek | None,
    made_by: str,
    reason: str,
) -> dict[str, Any]:
    by_day = {s.day: s for s in (answer.sessions if answer else [])}
    rx = rules.main_prescription(inputs.goals, inputs.experience)
    out_sessions = []
    llm_sessions = 0
    for s in sessions:
        llm = by_day.get(s.day)
        picked = _llm_main(s, llm) if needs_llm(s) else None
        if picked is not None:
            llm_sessions += 1
        others = picked if picked is not None else rules.main_items(s.reused or s.rules_main, rx)
        main = rules.main_items(s.core, rx) + [
            i for i in others if i["exercise_id"] not in {e["id"] for e in s.core}
        ]
        main = [
            overload.next_target(
                item,
                inputs.history.get(item["exercise_id"]),
                inputs.library_by_id(),
                inputs.adjustments.gentle,
            )
            for item in main
        ]
        out_sessions.append(
            {
                "day": s.day.isoformat(),
                "title": llm.title if llm and picked else rules.FOCUS_TITLES[s.focus],
                "focus": s.focus,
                "minutes": s.total_minutes,
                "explanation": llm.explanation if llm and picked else rules_explanation(s),
                "items": s.warm_cool + _numbered(main),
            }
        )
    week = block_week(inputs)
    if not sessions:
        rationale = (
            "No training days left this week (days off, or none set in Settings → Training)."
        )
    elif answer and llm_sessions:
        rationale = answer.rationale
    else:
        titles = ", ".join(rules.FOCUS_TITLES[s.focus] for s in sessions)
        rationale = (
            f"{len(sessions)} sessions this week ({titles}), "
            "each with a warm-up, main workout and cool-down."
        )
    if inputs.core_exercises and sessions:
        rationale += " Core lifts stay the same every week so the weights can go up."
        left_out = unusable_core(inputs)
        if left_out:
            rationale += (
                f" Left out of your core lifts: {', '.join(left_out)} (needs equipment you "
                "haven't listed, or is above your level). Change them in Settings → Training."
            )
    if sessions:
        rationale += f" Week {week} of {BLOCK_WEEKS} of this block."
    if inputs.adjustments.notes:
        rationale += " " + " ".join(inputs.adjustments.notes)
    return {
        "rationale": rationale[:2000],
        "made_by": made_by
        if llm_sessions
        else ("reused" if sessions and not any(needs_llm(s) for s in sessions) else "rules"),
        "reason": reason,
        "block_start": (inputs.block_start or inputs.week_start).isoformat(),
        "sessions": out_sessions,
    }


async def build_plan(
    inputs: PlanInputs,
    http: httpx2.AsyncClient | None,
    llm: LlmConfig | None,
    reason: str,
    rules_only_if_llm_fails: bool = True,
) -> dict[str, Any]:
    """The week's plan. Raises LlmError only if `rules_only_if_llm_fails` is False
    (so the API can hand the job to the worker instead of settling for rules)."""
    sessions = skeleton(inputs)
    if not any(needs_llm(s) for s in sessions) or llm is None or http is None:
        return assemble(inputs, sessions, None, "rules", reason)
    try:
        answer = await ask_json(
            http, llm, SYSTEM, build_prompt(inputs, sessions), LlmWeek, MAX_ANSWER_TOKENS
        )
    except LlmError:
        if not rules_only_if_llm_fails:
            raise
        return assemble(inputs, sessions, None, "rules", reason)
    return assemble(inputs, sessions, answer.value, answer.model, reason)
