"""Making a weekly workout plan (context/pages/workout-plan.md).

1. Rules (core/workouts/rules.py) set the shape: training days from today on,
   the split, phase minutes, and the warm-up, activation and cool-down exercises.
2. The LLM picks each session's main exercises from a short pre-filtered list,
   sets sets/reps/rest for the person's goals, experience and injuries, and
   explains the sessions and the week. Its answer is checked; anything that
   doesn't fit is replaced by the rules' choice.
3. Without a usable LLM answer, the rules make the whole plan.

The result is the JSON that public.save_workout_plan stores.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx2
from pydantic import BaseModel, Field

from core.llm import LlmConfig, LlmError, ask_json
from core.workouts import rules

SYSTEM = (
    "You are an experienced strength and conditioning coach planning a week of "
    "workouts for one adult. Choose safe, effective exercises, respect injuries and "
    "limitations, and follow current evidence-based guidance. Answer with JSON only."
)


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


class LlmSession(BaseModel):
    day: date
    title: str = Field(min_length=3, max_length=80)
    explanation: str = Field(min_length=10, max_length=400)
    # Compact, to fit Groq's free output limit:
    # [exercise_id, sets, reps_min, reps_max, rest_seconds]. Objects with those keys
    # are accepted too, in case the LLM answers that way.
    main: list[list[str | int] | dict[str, Any]] = Field(min_length=1, max_length=8)


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
    main_count: int
    candidates: list[dict[str, Any]]
    warm_cool: list[dict[str, Any]]
    rules_main: list[dict[str, Any]]


def skeleton(inputs: PlanInputs) -> list[Skeleton]:
    """Everything the rules decide, per training day."""
    kit = rules.kit_for(inputs.equipment, inputs.location)
    library = rules.usable_library(inputs.library, kit, inputs.experience)
    pools = rules.phase_pools(library, kit)
    days = rules.training_days(inputs.week_start, inputs.today, inputs.available_days)
    focuses = rules.split_for(len(days))
    sessions: list[Skeleton] = []
    used_main: set[str] = set()
    for day, focus in zip(days, focuses, strict=True):
        rng = rules.rng_for(inputs.profile_id, inputs.week_start, day)
        muscles = rules.FOCUS_MUSCLES[focus]
        minutes = rules.phase_minutes(inputs.minutes_per_session, inputs.goals)
        count = rules.main_exercise_count(minutes.main)
        candidates = rules.main_candidates(pools, muscles, rng, avoid=used_main)
        rules_main = candidates[:count]
        used_main |= {e["id"] for e in rules_main}
        sessions.append(
            Skeleton(
                day=day,
                focus=focus,
                muscles=muscles,
                minutes=minutes,
                total_minutes=inputs.minutes_per_session,
                main_count=count,
                candidates=candidates,
                warm_cool=rules.warm_and_cool(pools, muscles, minutes, rng),
                rules_main=rules_main,
            )
        )
    return sessions


def build_prompt(inputs: PlanInputs, sessions: list[Skeleton]) -> str:
    def line(e: dict[str, Any]) -> str:
        muscles = ", ".join(e.get("primary_muscles") or [])
        return f"  - {e['id']}: {e['name']} ({muscles}; {e.get('equipment') or 'body only'})"

    blocks = []
    for s in sessions:
        blocks.append(
            f"{s.day.isoformat()} ({s.day.strftime('%A')}): {rules.FOCUS_TITLES[s.focus]}, "
            f"{s.total_minutes} min ({s.minutes.main} min for the main workout). "
            f"Choose {s.main_count} main exercises from:\n" + "\n".join(map(line, s.candidates))
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
    return f"""Plan the main workout for each training day this week.

Person: {about}.
Injuries or limitations: {injuries}

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
    if len(chosen) < 2 or len(set(ids)) != len(ids) or len(chosen) > s.main_count + 1:
        return None
    return [
        {
            "phase": "main",
            "position": position,
            "exercise_id": exercise_id,
            "sets": sets,
            "reps_min": low,
            "reps_max": high,
            "rest_seconds": rest,
        }
        for position, (exercise_id, sets, low, high, rest) in enumerate(chosen)
    ]


def rules_explanation(s: Skeleton) -> str:
    muscles = ", ".join(s.muscles[:5])
    return (
        f"{rules.FOCUS_TITLES[s.focus]} session: warm up, then strength work for {muscles}, "
        "then stretch the muscles you used."
    )


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
        main = _llm_main(s, llm)
        if main is not None:
            llm_sessions += 1
        out_sessions.append(
            {
                "day": s.day.isoformat(),
                "title": llm.title if llm and main else rules.FOCUS_TITLES[s.focus],
                "focus": s.focus,
                "minutes": s.total_minutes,
                "explanation": llm.explanation if llm and main else rules_explanation(s),
                "items": s.warm_cool + (main or rules.main_items(s.rules_main, rx)),
            }
        )
    if not sessions:
        rationale = "No training days left this week: add days in Settings → Training."
    elif answer and llm_sessions:
        rationale = answer.rationale
    else:
        titles = ", ".join(rules.FOCUS_TITLES[s.focus] for s in sessions)
        rationale = (
            f"{len(sessions)} sessions this week ({titles}), "
            "each with a warm-up, main workout and cool-down."
        )
    return {
        "rationale": rationale,
        "made_by": made_by if llm_sessions else "rules",
        "reason": reason,
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
    if not sessions or llm is None or http is None:
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
