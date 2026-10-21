"""The fixed rules behind a weekly plan (context/pages/workout-plan.md).

Rules decide the shape of the week: which days, which split, how long each
phase is, which warm-up and cool-down exercises, and default sets and reps. The
LLM (core/workouts/generate.py) only picks the main exercises from a short,
pre-filtered list and explains the sessions; if it can't, these rules make the
whole plan on their own.
"""

import random
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

DAY_CODES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
MAX_SESSIONS = 6

# --- Equipment ------------------------------------------------------------------

# Settings equipment → the library's equipment names.
EQUIPMENT_MAP = {
    "dumbbells": {"dumbbell"},
    "barbell": {"barbell", "e-z curl bar"},
    "kettlebell": {"kettlebells"},
    "resistance_bands": {"bands"},
    "cable_machine": {"cable"},
}
FULL_GYM = {
    "dumbbell",
    "barbell",
    "e-z curl bar",
    "kettlebells",
    "bands",
    "cable",
    "machine",
    "medicine ball",
    "exercise ball",
    "foam roll",
    "other",
}
# Cardio machines by name, for people who have that machine.
CARDIO_MACHINES = {
    "treadmill": ("Walking, Treadmill", "Jogging, Treadmill"),
    "exercise_bike": ("Bicycling, Stationary", "Recumbent Bike"),
    "rowing_machine": ("Rowing, Stationary",),
}
# Gentle bodyweight warm-ups when there's no cardio machine.
BODYWEIGHT_CARDIO = (
    "Fast Skipping",
    "Double Leg Butt Kick",
    "Star Jump",
    "Mountain Climbers",
    "Carioca Quick Step",
)
# Stretches that move (good before a session) vs. ones held still (after it).
DYNAMIC_STRETCH = re.compile(
    r"circle|dynamic|swing|lunge|rotation|leg raise|world's greatest|hop|march|groiner|"
    r"carioca|skip|squat|walk",
    re.IGNORECASE,
)
STATIC_STRETCH = re.compile(r"stretch|pose|hug|lying|seated|kneeling|child", re.IGNORECASE)
# Bodyweight warm-up: rounds of drills, a minute each, instead of one long drill.
DRILL_SECONDS = 60
DRILL_REST_SECONDS = 15
NEEDS_BAR = re.compile(r"pull-?up|chin-?up|hanging|muscle up", re.IGNORECASE)
NEEDS_BENCH = re.compile(r"bench|incline|decline|preacher", re.IGNORECASE)


@dataclass(frozen=True)
class Kit:
    equipment: frozenset[str]
    has_bar: bool
    has_bench: bool
    full_gym: bool
    cardio_names: frozenset[str]


def kit_for(equipment: list[str], location: str | None) -> Kit:
    """What this person can use, in the library's terms."""
    full = "full_gym" in equipment or location == "gym"
    names: set[str] = set(FULL_GYM) if full else set()
    for item in equipment:
        names |= EQUIPMENT_MAP.get(item, set())
    cardio = {name for item in equipment for name in CARDIO_MACHINES.get(item, ())}
    if full:
        cardio |= {name for names_ in CARDIO_MACHINES.values() for name in names_}
    return Kit(
        equipment=frozenset(names),
        has_bar=full or "pull_up_bar" in equipment,
        has_bench=full or "bench" in equipment,
        full_gym=full,
        cardio_names=frozenset(cardio),
    )


LEVELS = {"beginner": 0, "intermediate": 1, "expert": 2}
EXPERIENCE_LEVEL = {"beginner": 0, "intermediate": 1, "advanced": 2}


def usable(exercise: dict[str, Any], kit: Kit, experience: str) -> bool:
    """Whether this person can do it: equipment they have, and not too advanced."""
    equipment = exercise.get("equipment")
    owned_machine = exercise["name"] in kit.cardio_names  # e.g. their treadmill
    if (
        equipment not in (None, "body only")
        and equipment not in kit.equipment
        and not owned_machine
    ):
        return False
    name = exercise["name"]
    if NEEDS_BAR.search(name) and not kit.has_bar:
        return False
    if NEEDS_BENCH.search(name) and equipment != "machine" and not kit.has_bench:
        return False
    level = LEVELS.get(exercise.get("level") or "beginner", 0)
    if level > EXPERIENCE_LEVEL.get(experience, 0):
        return False
    category = exercise.get("category")
    if category in ("olympic weightlifting", "strongman") and experience != "advanced":
        return False
    return True


# --- The week -------------------------------------------------------------------

FOCUS_MUSCLES = {
    "full_body": [
        "quadriceps",
        "glutes",
        "hamstrings",
        "chest",
        "lats",
        "middle back",
        "shoulders",
        "abdominals",
    ],
    "upper": ["chest", "lats", "middle back", "shoulders", "biceps", "triceps"],
    "lower": ["quadriceps", "hamstrings", "glutes", "calves", "abdominals", "lower back"],
    "push": ["chest", "shoulders", "triceps"],
    "pull": ["lats", "middle back", "biceps", "traps"],
    "legs": ["quadriceps", "hamstrings", "glutes", "calves", "abdominals"],
}
FOCUS_TITLES = {
    "full_body": "Full body",
    "upper": "Upper body",
    "lower": "Lower body",
    "push": "Push (chest, shoulders, triceps)",
    "pull": "Pull (back, biceps)",
    "legs": "Legs and core",
}
SPLITS = {
    1: ["full_body"],
    2: ["full_body", "full_body"],
    3: ["full_body", "full_body", "full_body"],
    4: ["upper", "lower", "upper", "lower"],
    5: ["upper", "lower", "push", "pull", "legs"],
    6: ["push", "pull", "legs", "push", "pull", "legs"],
}


def week_start_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def training_days(week_start: date, today: date, available: list[str]) -> list[date]:
    """The week's training days from today on (a plan made mid-week skips the past)."""
    days = [
        week_start + timedelta(days=offset)
        for offset in range(7)
        if DAY_CODES[offset] in available and week_start + timedelta(days=offset) >= today
    ]
    if len(days) > MAX_SESSIONS:
        # Keep a rest day: drop the last one.
        days = days[:MAX_SESSIONS]
    return days


def split_for(count: int) -> list[str]:
    return SPLITS.get(count, SPLITS[MAX_SESSIONS])[:count] if count else []


# --- Time and volume ---------------------------------------------------------------


@dataclass(frozen=True)
class PhaseMinutes:
    cardio: int
    mobility: int
    activation: int
    main: int
    cooldown: int


def phase_minutes(total: int, goals: list[str]) -> PhaseMinutes:
    """How a session's minutes are shared between the five phases."""
    cardio_share = 0.2 if {"lose_fat", "endurance"} & set(goals) else 0.12
    mobility_share = 0.15 if "mobility" in goals else 0.08
    cardio = max(3, round(total * cardio_share))
    mobility = max(3, round(total * mobility_share))
    activation = max(2, round(total * 0.07))
    cooldown = max(3, round(total * (0.12 if "mobility" in goals else 0.08)))
    main = max(5, total - cardio - mobility - activation - cooldown)
    return PhaseMinutes(cardio, mobility, activation, main, cooldown)


def main_exercise_count(main_minutes: int) -> int:
    # About 8 minutes per exercise (3 sets with rest).
    return max(2, min(7, round(main_minutes / 8)))


@dataclass(frozen=True)
class Prescription:
    sets: int
    reps_min: int
    reps_max: int
    rest_seconds: int


def main_prescription(goals: list[str], experience: str) -> Prescription:
    """Default sets, reps and rest for main exercises, by first matching goal."""
    goal_set = set(goals)
    if "get_stronger" in goal_set:
        rx = Prescription(4, 4, 6, 150) if experience != "beginner" else Prescription(3, 6, 8, 120)
    elif "build_muscle" in goal_set:
        rx = Prescription(4, 8, 12, 90) if experience != "beginner" else Prescription(3, 8, 12, 90)
    elif {"lose_fat", "endurance"} & goal_set:
        rx = Prescription(3, 12, 15, 60)
    else:
        rx = Prescription(3, 8, 12, 75)
    return rx


# --- Choosing exercises ------------------------------------------------------------


@dataclass
class Library:
    """The usable part of the exercise library for one person."""

    exercises: list[dict[str, Any]]
    by_id: dict[str, dict[str, Any]] = field(init=False)

    def __post_init__(self) -> None:
        self.by_id = {e["id"]: e for e in self.exercises}


def usable_library(rows: list[dict[str, Any]], kit: Kit, experience: str) -> Library:
    return Library([r for r in rows if usable(r, kit, experience)])


def _muscle_score(exercise: dict[str, Any], muscles: list[str]) -> float:
    primary = set(exercise.get("primary_muscles") or [])
    secondary = set(exercise.get("secondary_muscles") or [])
    return 2 * len(primary & set(muscles)) + 0.5 * len(secondary & set(muscles))


def rng_for(*parts: Any) -> random.Random:
    """Repeatable choices for a person and week, but different week to week."""
    return random.Random("|".join(str(p) for p in parts))


def pick(
    pool: list[dict[str, Any]],
    muscles: list[str],
    count: int,
    rng: random.Random,
    avoid: set[str] = frozenset(),
    spread: bool = True,
) -> list[dict[str, Any]]:
    """`count` exercises that best hit `muscles`, varied by `rng`, covering
    different muscles where possible."""
    scored = [
        (_muscle_score(e, muscles) + rng.random() * 0.9, e)
        for e in pool
        if e["id"] not in avoid and _muscle_score(e, muscles) > 0
    ]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    chosen: list[dict[str, Any]] = []
    hit: set[str] = set()
    for _, exercise in scored:
        if len(chosen) == count:
            break
        primary = set(exercise.get("primary_muscles") or [])
        if spread and primary <= hit and len(hit) < len(muscles):
            continue  # prefer a muscle not covered yet
        chosen.append(exercise)
        hit |= primary
    for _, exercise in scored:  # top up if spreading left gaps
        if len(chosen) == count:
            break
        if exercise not in chosen:
            chosen.append(exercise)
    return chosen


def phase_pools(library: Library, kit: Kit) -> dict[str, list[dict[str, Any]]]:
    """Which exercises can go in each phase."""
    stretches = [e for e in library.exercises if e.get("category") == "stretching"]
    strength = [
        e
        for e in library.exercises
        if e.get("category") in ("strength", "powerlifting", "olympic weightlifting")
    ]
    cardio = [e for e in library.exercises if e["name"] in kit.cardio_names]
    if not cardio:
        cardio = [e for e in library.exercises if e["name"] in BODYWEIGHT_CARDIO]
    activation = [
        e
        for e in strength
        if e.get("level") == "beginner"
        and e.get("equipment") in (None, "body only", "bands")
        and (e.get("mechanic") == "isolation" or e.get("force") == "static")
    ]
    main = [e for e in strength if e not in activation or e.get("mechanic") == "compound"]
    cooldown = [
        e
        for e in stretches
        if STATIC_STRETCH.search(e["name"]) and not DYNAMIC_STRETCH.search(e["name"])
    ]
    mobility = [e for e in stretches if DYNAMIC_STRETCH.search(e["name"])] or stretches
    return {
        "cardio": cardio,
        "mobility": mobility,
        "activation": activation,
        "main": main,
        "cooldown": cooldown or stretches,
    }


def main_candidates(
    pools: dict[str, list[dict[str, Any]]],
    muscles: list[str],
    rng: random.Random,
    avoid: set[str],
    size: int = 14,
) -> list[dict[str, Any]]:
    """A short list of good main exercises for the LLM to choose from (compound first)."""
    pool = pools["main"]
    compound = [e for e in pool if e.get("mechanic") == "compound"]
    others = [e for e in pool if e.get("mechanic") != "compound"]
    first = pick(compound, muscles, size * 2 // 3, rng, avoid)
    rest = pick(others, muscles, size - len(first), rng, avoid | {e["id"] for e in first})
    chosen = first + rest
    if len(chosen) < size:
        # Variety across the week is a preference: reuse exercises rather than run short.
        taken = {e["id"] for e in chosen}
        chosen += pick(pool, muscles, size - len(chosen), rng, taken)
    return chosen


def warm_and_cool(
    pools: dict[str, list[dict[str, Any]]],
    muscles: list[str],
    minutes: PhaseMinutes,
    rng: random.Random,
) -> list[dict[str, Any]]:
    """Cardio, mobility, activation and cooldown items (rules only)."""
    items: list[dict[str, Any]] = []

    def add(phase: str, exercises: list[dict[str, Any]], **rx: Any) -> None:
        for position, exercise in enumerate(exercises):
            items.append(
                {"phase": phase, "position": position, "exercise_id": exercise["id"], **rx}
            )

    cardio = pools["cardio"][:]
    rng.shuffle(cardio)
    if cardio and cardio[0]["name"] in BODYWEIGHT_CARDIO:
        # No machine: rounds of three gentle drills, a minute each.
        drill_round = (DRILL_SECONDS + DRILL_REST_SECONDS) * 3
        rounds = max(1, min(4, round(minutes.cardio * 60 / drill_round)))
        add(
            "cardio",
            cardio[:3],
            sets=rounds,
            duration_seconds=DRILL_SECONDS,
            rest_seconds=DRILL_REST_SECONDS,
        )
    else:
        add("cardio", cardio[:1], sets=1, duration_seconds=minutes.cardio * 60)
    mobility_count = max(2, min(4, minutes.mobility // 2))
    add(
        "mobility",
        pick(pools["mobility"], muscles, mobility_count, rng),
        sets=1,
        duration_seconds=45,
    )
    for position, exercise in enumerate(pick(pools["activation"], muscles, 2, rng)):
        # Holds (planks, bridges) are timed; everything else is reps.
        held = exercise.get("force") == "static"
        items.append(
            {
                "phase": "activation",
                "position": position,
                "exercise_id": exercise["id"],
                "sets": 2,
                "rest_seconds": 30,
                **({"duration_seconds": 30} if held else {"reps_min": 12, "reps_max": 15}),
            }
        )
    cooldown_count = max(2, min(4, minutes.cooldown // 2))
    used = {i["exercise_id"] for i in items}
    add(
        "cooldown",
        pick(pools["cooldown"], muscles, cooldown_count, rng, avoid=used),
        sets=1,
        duration_seconds=45,
    )
    return items


def main_items(exercises: list[dict[str, Any]], rx: Prescription) -> list[dict[str, Any]]:
    return [
        {
            "phase": "main",
            "position": position,
            "exercise_id": exercise["id"],
            "sets": rx.sets,
            "reps_min": rx.reps_min,
            "reps_max": rx.reps_max,
            "rest_seconds": rx.rest_seconds,
        }
        for position, exercise in enumerate(exercises)
    ]
