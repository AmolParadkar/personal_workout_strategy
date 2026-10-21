"""Progressive overload: next week's target for a main exercise, from what was
actually done last time (context/pages/workout-plan.md, "Progressive overload").

- Weighted exercises: all sets at the top of the rep range (or an "easy" session)
  → add a step of weight; most sets short of the range, or "too hard" → a step
  lighter; otherwise the same weight, aiming for more reps.
- Bodyweight and band exercises: all sets at the top of the range → the rep
  range moves up by 2.
- A gentle week (back from a medical pause, or asked for): one set fewer and
  about 15% lighter.
"""

from dataclasses import dataclass
from typing import Any

# Weight steps by equipment (kg). Dumbbells and kettlebells are per hand/bell.
STEPS = {
    "barbell": 2.5,
    "e-z curl bar": 2.5,
    "machine": 2.5,
    "cable": 2.5,
    "dumbbell": 2.0,
    "kettlebells": 4.0,
}
MAX_REPS = 30


@dataclass(frozen=True)
class LastTime:
    """The most recent time an exercise was logged."""

    sets: list[tuple[int | None, float | None]]  # (reps, load_kg) per set
    reps_min: int | None
    reps_max: int | None
    effort: str | None  # easy / right / too_hard (the session's rating)


def _kg(value: float) -> float:
    return round(value * 2) / 2  # to the nearest 0.5 kg


def next_target(
    item: dict[str, Any],
    last: LastTime | None,
    library: dict[str, dict[str, Any]],
    gentle: bool = False,
) -> dict[str, Any]:
    """The item with target load, reps and a short note set from last time."""
    item = dict(item)
    if last and last.sets:
        reps = [r for r, _ in last.sets if r is not None]
        loads = [kg for _, kg in last.sets if kg]
        low = last.reps_min or item.get("reps_min") or 1
        high = last.reps_max or item.get("reps_max") or low
        all_top = bool(reps) and all(r >= high for r in reps)
        all_in_range = bool(reps) and all(r >= low for r in reps)
        mostly_short = bool(reps) and sum(r < low for r in reps) > len(reps) / 2
        step = STEPS.get((library.get(item["exercise_id"]) or {}).get("equipment") or "")
        done = f"{len(reps)}×{max(reps)}" if reps else "it"
        if loads and step:
            top = max(loads)
            if last.effort == "too_hard" or mostly_short:
                target = max(0.0, top - step) if mostly_short else top
                item["target_load_kg"] = _kg(target)
                item["notes"] = (
                    f"Last time {done} at {top:g} kg felt hard: {target:g} kg, focus on form."
                )
            elif all_top or (last.effort == "easy" and all_in_range):
                item["target_load_kg"] = _kg(top + step)
                item["notes"] = f"Last time {done} at {top:g} kg: try {top + step:g} kg."
            else:
                item["target_load_kg"] = _kg(top)
                item["notes"] = f"Last time {done} at {top:g} kg: same weight, aim for more reps."
        elif reps and all_top and last.effort != "too_hard" and item.get("reps_max"):
            new_low = min(MAX_REPS, (item.get("reps_min") or low) + 2)
            new_high = min(MAX_REPS, (item.get("reps_max") or high) + 2)
            item["reps_min"], item["reps_max"] = new_low, new_high
            item["notes"] = f"Last time you hit {max(reps)} reps: aim for {new_low}–{new_high}."
    if gentle:
        if item.get("sets"):
            item["sets"] = max(2, item["sets"] - 1)
        if item.get("target_load_kg"):
            item["target_load_kg"] = _kg(item["target_load_kg"] * 0.85)
        item["notes"] = ("Easing back in: lighter than usual. " + (item.get("notes") or "")).strip()
    return item
