"""Making a weekly meal plan. The rules work out each day's targets, which meals
the day has, which foods the person can have, the portions and every nutrient
number; the LLM only chooses dishes from candidate lists, for variety and to fit
the person's cuisines and cooking time. Without an LLM the rules choose too.
Spec: context/pages/nutrition-plan.md."""

import random
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import httpx2
from pydantic import BaseModel

from core.llm import LlmConfig, LlmError, ask_json
from core.nutrition import rules
from core.nutrition.rules import Food, Portion
from core.nutrition.targets import Body, Targets, daily_targets

# Candidates shown to the LLM per kind (a fresh sample each week, for variety).
SAMPLE = {"b": 24, "m": 32, "s": 16, "x": 12, "n": 18}
KIND_LABELS = {
    "b": "Breakfast dishes",
    "m": "Main dishes (curries, dals, meat, eggs, vegetables)",
    "s": "Breads and rice",
    "x": "Salads and raitas",
    "n": "Snacks and fruit",
}
MAX_ANSWER_TOKENS = 900
PROTEIN_SHORT = 0.9  # top up protein when a day is below 90% of its target
MEAL_OVER = 1.2  # a protein add-on may take a meal at most 20% over its share
PLAIN_STAPLE = re.compile(r"chapati|\broti\b|boiled rice|brown rice|phulka", re.IGNORECASE)
# Dishes getting more of their calories from fat than this aren't planned
# (nuts, chosen on purpose, are the exception).
MAX_FAT_SHARE = 0.55
# Protein per kcal that counts as protein-rich (e.g. 10 g in a 150 kcal bowl).
PROTEIN_RICH = 0.065


def fat_share(food: Food) -> float:
    kcal = float(food.get("kcal") or 0)
    return 9 * float(food.get("fat_g") or 0) / kcal if kcal else 0


def protein_density(food: Food) -> float:
    kcal = float(food.get("kcal") or 0)
    return float(food.get("protein_g") or 0) / kcal if kcal else 0


SYSTEM = (
    "You are a dietitian planning a week of home meals. You choose dishes only from "
    "the lists given, by their codes. Answer with JSON only."
)


@dataclass
class MealInputs:
    profile_id: str
    week_start: date
    today: date
    body: Body | None
    diet_type: str | None
    cuisines: list[str]
    allergies: list[str]
    dislikes: list[str]
    meals_per_day: int | None
    cooking_minutes: int | None
    # Planned training per day (minutes), from the workout plan.
    training: dict[date, int]
    foods: list[Food]
    seed: str = ""
    # Mains from last week, used less this week.
    recent: set[str] = field(default_factory=set)

    def days(self) -> list[date]:
        start = max(self.today, self.week_start)
        end = self.week_start + timedelta(days=6)
        return [start + timedelta(days=n) for n in range((end - start).days + 1)]

    def slots(self) -> list[str]:
        return rules.slots_for(self.meals_per_day)


@dataclass
class Candidates:
    by_kind: dict[str, list[Food]]
    protein: list[Food]

    def code_map(self) -> dict[str, Food]:
        return {f"{k}{n}": f for k, foods in self.by_kind.items() for n, f in enumerate(foods)}


def candidates(inputs: MealInputs) -> Candidates:
    avoid = rules.avoid_words(inputs.allergies, inputs.dislikes)
    ok = [f for f in inputs.foods if rules.allowed(f, inputs.diet_type, avoid)]

    def role(*names: str) -> list[Food]:
        return [
            f
            for f in ok
            if f.get("role") in names and (f.get("alias") or fat_share(f) <= MAX_FAT_SHARE)
        ]

    # The smallest portion has to fit the meal: a 400 kcal dosa is too much for a
    # 350 kcal breakfast. Measured against a rest day, the smallest day.
    if inputs.body is not None:
        slots = inputs.slots()
        day_kcal = daily_targets(inputs.body).kcal
        shares = dict(zip(slots, rules.slot_kcal(day_kcal, slots), strict=True))
        room = {
            "b": 1.1 * shares.get("breakfast", 0),
            "m": 0.7 * max(shares.get("lunch", 0), shares.get("dinner", 0)),
            "s": 0.6 * max(shares.get("lunch", 0), shares.get("dinner", 0)),
            "x": 0.4 * max(shares.get("lunch", 0), shares.get("dinner", 0)),
            "n": 1.3 * shares.get("snack", shares.get("breakfast", 0)),
        }
    else:
        room = {}

    def fits(kind: str, food: Food) -> bool:
        smallest = rules.nutrients(food, rules.step(food))["kcal"]
        return kind not in room or not room[kind] or smallest <= room[kind]

    rng = random.Random(f"{inputs.profile_id}:{inputs.week_start}:{inputs.seed}")
    by_kind = {
        "b": role("breakfast"),
        "m": role("main"),
        "s": role("staple"),
        "x": role("salad"),
        "n": role("snack", "fruit") + [f for f in role("protein") if f.get("alias")],
    }
    for kind, foods in by_kind.items():
        foods = [f for f in foods if fits(kind, f)]
        rng.shuffle(foods)
        # Last week's mains go to the back, so this week tends to differ.
        foods.sort(key=lambda f: f["id"] in inputs.recent)
        if kind == "s":
            # Plain chapati and rice always make the list.
            foods.sort(key=lambda f: not PLAIN_STAPLE.search(f["name"]))
        if kind in ("m", "b"):
            # Protein-rich dishes first.
            foods.sort(key=lambda f: protein_density(f) < PROTEIN_RICH)
        by_kind[kind] = foods[: SAMPLE[kind]]
    return Candidates(by_kind=by_kind, protein=rules.protein_foods(ok, inputs.diet_type))


# --- Choosing dishes -------------------------------------------------------------------------

Picks = dict[date, list[list[Food]]]


def rules_picks(inputs: MealInputs, c: Candidates) -> Picks:
    """Dishes chosen by rotation: no main twice within two days, lunch and dinner
    differ, plain chapati or rice most days, a salad or raita with lunch."""
    mains, breakfasts = c.by_kind["m"], c.by_kind["b"]
    staples = [f for f in c.by_kind["s"] if PLAIN_STAPLE.search(f["name"])] or c.by_kind["s"]
    salads, snacks = c.by_kind["x"], c.by_kind["n"]
    picks: Picks = {}
    recent: list[str] = []
    counters = {"m": 0, "b": 0, "s": 0, "x": 0, "n": 0}

    def next_of(kind: str, pool: list[Food], avoid: set[str] = frozenset()) -> Food | None:
        if not pool:
            return None
        for _ in range(len(pool)):
            food = pool[counters[kind] % len(pool)]
            counters[kind] += 1
            if food["id"] not in avoid:
                return food
        return pool[0]

    for day in inputs.days():
        meals = []
        for slot in inputs.slots():
            if slot == "breakfast":
                meals.append([f for f in [next_of("b", breakfasts)] if f])
            elif slot in ("lunch", "dinner"):
                main = next_of("m", mains, set(recent[-3:]))
                if main:
                    recent.append(main["id"])
                staple = next_of("s", staples)
                side = next_of("x", salads) if slot == "lunch" else None
                meals.append([f for f in (main, staple, side) if f])
            else:
                meals.append([f for f in [next_of("n", snacks)] if f])
        picks[day] = meals
    return picks


class LlmMealWeek(BaseModel):
    note: str = ""
    # day (YYYY-MM-DD) → one list of codes per meal, in order.
    days: dict[str, list[list[str]]]


def build_prompt(inputs: MealInputs, c: Candidates, targets: dict[date, Targets]) -> str:
    def line(code: str, f: Food) -> str:
        n = rules.nutrients(f, 1)
        return (
            f"{code} {rules.display_name(f)} ({f.get('serving_label') or 'serving'}, "
            f"{n['kcal']:.0f} kcal, {n['protein_g']:.0f} g protein)"
        )

    lists = "\n\n".join(
        f"{KIND_LABELS[kind]}:\n" + "\n".join(line(f"{kind}{n}", f) for n, f in enumerate(foods))
        for kind, foods in c.by_kind.items()
        if foods
    )
    slots = inputs.slots()
    shape = {
        "breakfast": "1 b code (optionally 1 n fruit)",
        "lunch": "1 m + 1 s (+ optionally 1 x)",
        "dinner": "1 m + 1 s (+ optionally 1 x)",
        "snack": "1 n code",
    }
    days = "\n".join(
        f"{d.isoformat()} ({d.strftime('%A')}): {targets[d].kcal} kcal, "
        f"{targets[d].protein_g} g protein"
        + (f", training {inputs.training[d]} min" if inputs.training.get(d) else ", rest day")
        for d in inputs.days()
    )
    cuisines = ", ".join(inputs.cuisines) or "Indian home cooking"
    cooking = f"{inputs.cooking_minutes} minutes" if inputs.cooking_minutes else "not given"
    return f"""Choose this week's meals.

Cuisines they like: {cuisines}. Time to cook per day: {cooking}.
Meals each day, in order: {", ".join(slots)}.
Each meal is: {"; ".join(f"{s}: {shape[s]}" for s in dict.fromkeys(slots))}.
Days and targets:
{days}

Portions are worked out afterwards, so just choose dishes. Favour dishes with more
protein, vary the week (no main dish twice within two days; lunch and dinner differ),
keep busy days simple, and prefer everyday home food over party dishes.

{lists}

Return JSON: {{"note": "one sentence on how the week fits them",
"days": {{"YYYY-MM-DD": [["codes for meal 1"], ["codes for meal 2"], ...]}}}}"""


def llm_picks(inputs: MealInputs, c: Candidates, answer: LlmMealWeek, fallback: Picks) -> Picks:
    """The LLM's choices where they're valid, the rules' choices elsewhere."""
    codes = c.code_map()
    picks: Picks = {}
    for day in inputs.days():
        chosen = answer.days.get(day.isoformat()) or []
        meals = []
        for n, slot in enumerate(inputs.slots()):
            raw = chosen[n] if n < len(chosen) and isinstance(chosen[n], list) else []
            foods = [codes[str(code)] for code in raw if str(code) in codes]
            kinds = [k for code in raw for k in [str(code)[:1]] if str(code) in codes]
            valid = (
                (slot == "breakfast" and kinds.count("b") == 1 and len(foods) <= 2)
                or (
                    slot in ("lunch", "dinner")
                    and kinds.count("m") == 1
                    and kinds.count("s") == 1
                    and kinds.count("x") <= 1
                    and len(foods) <= 3
                )
                or (slot == "snack" and len(foods) == 1 and kinds == ["n"])
            )
            if valid:
                # Main first, then staple, then the rest.
                order = {"b": 0, "m": 0, "s": 1, "x": 2, "n": 3}
                pairs = sorted(zip(kinds, foods, strict=True), key=lambda p: order[p[0]])
                meals.append([f for _, f in pairs])
            else:
                meals.append(fallback[day][n])
        picks[day] = meals
    return picks


# --- Portions and the finished plan ------------------------------------------------------------


def portions_for(slot: str, foods: list[Food]) -> list[Portion]:
    if not foods:
        return []
    if slot in ("lunch", "dinner"):
        main, rest = foods[0], foods[1:]
        staple = rest[0] if rest else None
        out = [Portion(main, 1, flexible=staple is None)]
        if staple:
            out.append(Portion(staple, 1, flexible=True))
        out += [Portion(f, 1) for f in rest[1:]]
        return out
    # Breakfast and snacks: the first food carries the size; extras are one serving.
    return [Portion(foods[0], 1, flexible=True)] + [Portion(f, 1) for f in foods[1:]]


def size(slot: str, portions: list[Portion], target: float) -> list[Portion]:
    rules.size_meal(portions, target)
    total = rules.meal_totals(portions)["kcal"]
    if slot in ("lunch", "dinner") and portions and total < 0.85 * target:
        # The staple alone can't fill the meal: a bigger helping of the main.
        portions[0].servings = rules.snap(portions[0].food, 1.5, most=2)
        rules.size_meal(portions, target)
    if slot in ("lunch", "dinner") and portions and total > 1.15 * target:
        # Even the smallest staple overshoots: drop the side, then a smaller main.
        if len(portions) > 2 and portions[2].food.get("role") == "salad":
            portions.pop(2)
        portions[0].servings = rules.snap(portions[0].food, 0.5)
        rules.size_meal(portions, target)
    if slot == "snack":
        for p in portions:
            p.servings = rules.snap(p.food, p.servings, most=3 if p.food.get("countable") else 1.5)
    return portions


def top_up_protein(
    meals: list[tuple[str, list[Portion], float]], target: Targets, protein: list[Food]
) -> dict[int, str]:
    """Add a simple protein (eggs, chicken, curd, …) to meals until the day is
    close to its protein target; staples shrink to keep the calories. Returns a
    note for each meal that got one."""

    def day_protein() -> float:
        return sum(rules.meal_totals(p)["protein_g"] for _, p, _ in meals)

    notes: dict[int, str] = {}
    order = sorted(
        range(len(meals)),
        key=lambda n: ["lunch", "dinner", "breakfast", "snack"].index(meals[n][0]),
    )
    for n in order:
        short = target.protein_g * PROTEIN_SHORT - day_protein()
        if short <= 0:
            break
        slot, portions, kcal = meals[n]
        used = {p.food["id"] for _, ps, _ in meals for p in ps}
        # A meat dish (and breakfast) gets eggs or curd, not more meat.
        has_meat = slot == "breakfast" or any(p.food["diet"] == "non_vegetarian" for p in portions)
        food = next(
            (
                f
                for f in protein
                if f["id"] not in used and not (has_meat and f["diet"] == "non_vegetarian")
            ),
            None,
        )
        if not food or not portions:
            continue
        per = rules.nutrients(food, 1)["protein_g"] or 1
        servings = rules.snap(food, short / per, most=3 if food.get("countable") else 2)
        added = Portion(food, servings)
        portions.append(added)
        size(slot, portions, kcal)
        # Keep the meal near its share: a smaller add-on, or none if even the
        # smallest one is too much (the staple is already as small as it goes).
        while rules.meal_totals(portions)["kcal"] > MEAL_OVER * kcal:
            if added.servings > rules.step(food):
                added.servings -= rules.step(food)
                size(slot, portions, kcal)
            else:
                portions.remove(added)
                size(slot, portions, kcal)
                break
        if added in portions:
            notes[n] = f"{rules.display_name(food)} added to reach your protein target."
    return notes


def day_plan(
    inputs: MealInputs, day: date, target: Targets, picked: list[list[Food]], protein: list[Food]
) -> dict[str, Any]:
    slots = inputs.slots()
    shares = rules.slot_kcal(target.kcal, slots)
    meals = [
        (slot, size(slot, portions_for(slot, foods), kcal), kcal)
        for slot, foods, kcal in zip(slots, picked, shares, strict=True)
    ]
    notes = top_up_protein(meals, target, protein)
    out = []
    for position, (slot, portions, _) in enumerate(meals):
        meal = rules.meal_json(slot, position, portions, notes.get(position))
        meal.pop("_lead", None)
        out.append(meal)
    return {"day": day.isoformat(), "targets": target.as_json(), "meals": out}


def week_targets(inputs: MealInputs) -> dict[date, Targets]:
    assert inputs.body is not None
    return {d: daily_targets(inputs.body, inputs.training.get(d, 0)) for d in inputs.days()}


def assemble(
    inputs: MealInputs,
    c: Candidates,
    targets: dict[date, Targets],
    picks: Picks,
    made_by: str,
    reason: str,
    note: str | None,
) -> dict[str, Any]:
    days = [day_plan(inputs, d, targets[d], picks[d], c.protein) for d in inputs.days()]
    rest = [t for d, t in targets.items() if not inputs.training.get(d)]
    trained = [t for d, t in targets.items() if inputs.training.get(d)]
    summary = (
        f"About {rest[0].kcal if rest else trained[0].kcal:,} kcal and "
        f"{(rest or trained)[0].protein_g} g protein a day"
        if targets
        else "No days left to plan this week"
    )
    if rest and trained:
        extra = max(t.kcal for t in trained) - rest[0].kcal
        summary += f"; up to {extra:,} kcal more on training days, mostly from carbs"
    rationale = (note.strip() + " " if note else "") + summary + "."
    if not c.protein or not c.by_kind["m"]:
        rationale += " Few dishes fit your diet and allergies, so the week repeats more."
    return {
        "rationale": rationale[:2000],
        "made_by": made_by,
        "reason": reason,
        "days": days,
    }


async def build_plan(
    inputs: MealInputs,
    http: httpx2.AsyncClient | None,
    llm: LlmConfig | None,
    reason: str,
    rules_only_if_llm_fails: bool = True,
) -> dict[str, Any]:
    """The week's meals. Raises LlmError only if `rules_only_if_llm_fails` is False
    (so the API can hand the job to the worker instead of settling for rules)."""
    c = candidates(inputs)
    targets = week_targets(inputs)
    fallback = rules_picks(inputs, c)
    if not inputs.days() or llm is None or http is None:
        return assemble(inputs, c, targets, fallback, "rules", reason, None)
    try:
        answer = await ask_json(
            http, llm, SYSTEM, build_prompt(inputs, c, targets), LlmMealWeek, MAX_ANSWER_TOKENS
        )
    except LlmError:
        if not rules_only_if_llm_fails:
            raise
        return assemble(inputs, c, targets, fallback, "rules", reason, None)
    picks = llm_picks(inputs, c, answer.value, fallback)
    return assemble(inputs, c, targets, picks, answer.model, reason, answer.value.note)
