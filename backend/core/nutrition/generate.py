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
SAMPLE = {"b": 22, "m": 28, "v": 22, "s": 14, "x": 12, "n": 16}
KIND_LABELS = {
    "b": "Breakfast dishes",
    "m": "Protein dishes (dals, beans, paneer, eggs, meat, fish)",
    "v": "Vegetable dishes (sabzis)",
    "s": "Breads and rice",
    "x": "Salads and raitas",
    "n": "Snacks and fruit",
}
# Most times one dish appears in a week (staples like chapati and rice excepted).
MAX_PER_WEEK = {"b": 2, "m": 2, "v": 2, "x": 2, "n": 3}
MAX_ANSWER_TOKENS = 1100
PROTEIN_SHORT = 0.9  # top up protein when a day is below 90% of its target
MEAL_OVER = 1.2  # a protein add-on may take a meal at most 20% over its share
PLAIN_STAPLE = re.compile(r"chapati|\broti\b|boiled rice|brown rice|phulka", re.IGNORECASE)
PROTEIN_WORDS = re.compile(
    r"\b(dal|daal|dhal|rajma|chole|chana|channa|lobia|moong|masoor|urad|arhar|toor|sambar|"
    r"paneer|tofu|soya|sprout\w*|egg\w*|keema|chicken|mutton|fish|prawn|kadhi)\b",
    re.IGNORECASE,
)
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


def main_kind(food: Food) -> str:
    """'m' for a protein dish (dal, beans, paneer, eggs, meat), 'v' for a vegetable
    dish (sabzi): lunch has one of each."""
    pulses = sum(
        float(i.get("amount") or 0)
        for i in food.get("ingredients") or []
        if i.get("group") == "Pulses" and i.get("unit") == "g"
    )
    if (
        food["diet"] != "vegetarian"
        or pulses >= 20
        or protein_density(food) >= 0.05
        or PROTEIN_WORDS.search(food["name"])
    ):
        return "m"
    return "v"


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
    # From the chat: what they asked for this week, and words to leave out.
    request: str = ""
    extra_avoid: list[str] = field(default_factory=list)

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

    def kind_of(self, food: Food) -> str:
        return next(k for k, foods in self.by_kind.items() if food in foods)


def candidates(inputs: MealInputs) -> Candidates:
    avoid = rules.avoid_words(inputs.allergies, [*inputs.dislikes, *inputs.extra_avoid])
    ok = [f for f in inputs.foods if rules.allowed(f, inputs.diet_type, avoid)]

    def role(*names: str) -> list[Food]:
        return [
            f
            for f in ok
            if f.get("role") in names
            and (f.get("alias") or f.get("source") == "custom" or fat_share(f) <= MAX_FAT_SHARE)
        ]

    # The smallest portion has to fit the meal: a 400 kcal dosa is too much for a
    # 350 kcal breakfast. Measured against a rest day, the smallest day.
    if inputs.body is not None:
        slots = inputs.slots()
        day_kcal = daily_targets(inputs.body).kcal
        shares = dict(zip(slots, rules.slot_kcal(day_kcal, slots), strict=True))
        main = max(shares.get("lunch", 0), shares.get("dinner", 0))
        room = {
            "b": 1.1 * shares.get("breakfast", 0),
            "m": 0.6 * main,
            "v": 0.45 * main,
            "s": 0.6 * main,
            "x": 0.35 * main,
            "n": 1.3 * shares.get("snack", shares.get("breakfast", 0)),
        }
    else:
        room = {}

    def fits(kind: str, food: Food) -> bool:
        smallest = rules.nutrients(food, rules.step(food))["kcal"]
        return kind not in room or not room[kind] or smallest <= room[kind]

    mains = role("main")
    rng = random.Random(f"{inputs.profile_id}:{inputs.week_start}:{inputs.seed}")
    by_kind = {
        "b": role("breakfast"),
        "m": [f for f in mains if main_kind(f) == "m"],
        "v": [f for f in mains if main_kind(f) == "v"],
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
        # The household's own dishes always make the list.
        foods.sort(key=lambda f: f.get("source") != "custom")
        by_kind[kind] = foods[: SAMPLE[kind]]
    return Candidates(by_kind=by_kind, protein=rules.protein_foods(ok, inputs.diet_type))


# --- Choosing dishes -------------------------------------------------------------------------

Picks = dict[date, list[list[Food]]]
# The order dishes sit in a meal: the main, then the staple (resized to fit),
# then the vegetable dish and salad.
ORDER = {"b": 0, "m": 0, "s": 1, "v": 2, "x": 3, "n": 4}


class Rotation:
    """Hands out dishes in turn, at most MAX_PER_WEEK times each, not repeating
    the last few."""

    def __init__(self, c: Candidates):
        self.c = c
        self.used: dict[str, int] = {}
        self.turn = dict.fromkeys(c.by_kind, 0)

    def take(self, kind: str, avoid: set[str] = frozenset(), pool=None) -> Food | None:
        pool = pool if pool is not None else self.c.by_kind[kind]
        if not pool:
            return None
        cap = MAX_PER_WEEK.get(kind)
        for _ in range(len(pool)):
            food = pool[self.turn[kind] % len(pool)]
            self.turn[kind] += 1
            if food["id"] in avoid or (cap and self.used.get(food["id"], 0) >= cap):
                continue
            self.used[food["id"]] = self.used.get(food["id"], 0) + 1
            return food
        # Everything's been used enough (few dishes fit): repeat the least used.
        food = min(pool, key=lambda f: (f["id"] in avoid, self.used.get(f["id"], 0)))
        self.used[food["id"]] = self.used.get(food["id"], 0) + 1
        return food

    def allow(self, kind: str, food: Food) -> bool:
        cap = MAX_PER_WEEK.get(kind)
        if cap and self.used.get(food["id"], 0) >= cap:
            return False
        self.used[food["id"]] = self.used.get(food["id"], 0) + 1
        return True


def shape(slot: str, foods: list[Food], c: Candidates) -> list[Food]:
    return sorted(foods, key=lambda f: ORDER[c.kind_of(f)])


def rules_picks(inputs: MealInputs, c: Candidates) -> Picks:
    """Dishes chosen in turn: a protein dish, a vegetable dish, chapati or rice and
    a raita or salad for lunch; a protein dish and chapati or rice (and a
    vegetable dish when there are enough) for dinner; nothing more than twice a week."""
    staples = [f for f in c.by_kind["s"] if PLAIN_STAPLE.search(f["name"])] or c.by_kind["s"]
    turn = Rotation(c)
    recent: list[str] = []
    picks: Picks = {}
    for day in inputs.days():
        meals = []
        for slot in inputs.slots():
            if slot == "breakfast":
                foods = [turn.take("b")]
            elif slot in ("lunch", "dinner"):
                main = turn.take("m", set(recent[-2:]))
                if main:
                    recent.append(main["id"])
                foods = [main, turn.take("s", pool=staples), turn.take("v")]
                if slot == "lunch":
                    foods.append(turn.take("x"))
            else:
                foods = [turn.take("n")]
            meals.append(shape(slot, [f for f in foods if f], c))
        picks[day] = meals
    return picks


class LlmMealWeek(BaseModel):
    note: str = ""
    # day (YYYY-MM-DD) → one list of codes per meal, in order.
    days: dict[str, list[list[str]]]


SHAPES = {
    "breakfast": "1 b (optionally + 1 n fruit)",
    "lunch": "1 m + 1 v + 1 s + 1 x",
    "dinner": "1 m + 1 s (optionally + 1 v)",
    "snack": "1 n",
}


def build_prompt(inputs: MealInputs, c: Candidates, targets: dict[date, Targets]) -> str:
    def line(code: str, f: Food) -> str:
        n = rules.nutrients(f, 1)
        mine = " (their own dish)" if f.get("source") == "custom" else ""
        return (
            f"{code} {rules.display_name(f)}{mine} ({f.get('serving_label') or 'serving'}, "
            f"{n['kcal']:.0f} kcal, {n['protein_g']:.0f} g protein)"
        )

    lists = "\n\n".join(
        f"{KIND_LABELS[kind]}:\n" + "\n".join(line(f"{kind}{n}", f) for n, f in enumerate(foods))
        for kind, foods in c.by_kind.items()
        if foods
    )
    slots = inputs.slots()
    days = "\n".join(
        f"{d.isoformat()} ({d.strftime('%A')}): {targets[d].kcal} kcal, "
        f"{targets[d].protein_g} g protein"
        + (f", training {inputs.training[d]} min" if inputs.training.get(d) else ", rest day")
        for d in inputs.days()
    )
    cuisines = ", ".join(inputs.cuisines) or "Indian home cooking"
    cooking = f"{inputs.cooking_minutes} minutes" if inputs.cooking_minutes else "not given"
    request = (
        f"\nTheir request for this week (follow it): {inputs.request.strip()}\n"
        if inputs.request.strip()
        else ""
    )
    return f"""Choose this week's meals.

Cuisines they like: {cuisines}. Time to cook per day: {cooking}.
Meals each day, in order: {", ".join(slots)}.
Each meal is: {"; ".join(f"{s}: {SHAPES[s]}" for s in dict.fromkeys(slots))}.
Days and targets:
{days}
{request}
Portions are worked out afterwards, so just choose dishes. Favour dishes with more
protein and use their own dishes when they fit. Vary the week: no dish more than twice
(chapati and rice excepted), lunch and dinner differ, and keep busy days simple.
Prefer everyday home food over party dishes.

{lists}

Return JSON: {{"note": "one sentence on how the week fits them",
"days": {{"YYYY-MM-DD": [["codes for meal 1"], ["codes for meal 2"], ...]}}}}"""


def _valid(slot: str, kinds: list[str]) -> bool:
    count = kinds.count
    if slot == "breakfast":
        return count("b") == 1 and len(kinds) <= 2 and set(kinds) <= {"b", "n"}
    if slot == "snack":
        return kinds == ["n"]
    return (
        count("m") == 1
        and count("s") == 1
        and count("v") <= 1
        and count("x") <= 1
        and set(kinds) <= {"m", "s", "v", "x"}
    )


def llm_picks(inputs: MealInputs, c: Candidates, answer: LlmMealWeek, fallback: Picks) -> Picks:
    """The LLM's choices where they're valid (and no dish more than twice a week),
    the rules' choices elsewhere."""
    codes = c.code_map()
    turn = Rotation(c)
    picks: Picks = {}
    for day in inputs.days():
        chosen = answer.days.get(day.isoformat()) or []
        meals = []
        for n, slot in enumerate(inputs.slots()):
            raw = chosen[n] if n < len(chosen) and isinstance(chosen[n], list) else []
            pairs = [(str(code)[:1], codes[str(code)]) for code in raw if str(code) in codes]
            if _valid(slot, [k for k, _ in pairs]):
                foods = []
                for kind, food in pairs:
                    if kind == "s" or turn.allow(kind, food):
                        foods.append(food)
                    else:
                        # Used twice already: another dish of the same kind.
                        swap = turn.take(kind)
                        if swap:
                            foods.append(swap)
                meals.append(shape(slot, foods, c))
            else:
                meals.append(fallback[day][n])
        picks[day] = meals
    return picks


# --- Portions and the finished plan ------------------------------------------------------------


def portions_for(slot: str, foods: list[Food]) -> list[Portion]:
    """Lunch and dinner: the staple carries the size (the main if there's none);
    breakfast and snacks: the first food. Everything else is one serving."""
    if not foods:
        return []
    if slot in ("lunch", "dinner"):
        staple = 1 if len(foods) > 1 and foods[1].get("role") == "staple" else None
        return [
            Portion(f, 1, flexible=(n == staple) or (staple is None and n == 0))
            for n, f in enumerate(foods)
        ]
    return [Portion(foods[0], 1, flexible=True)] + [Portion(f, 1) for f in foods[1:]]


def size(slot: str, portions: list[Portion], target: float) -> list[Portion]:
    rules.size_meal(portions, target)
    if slot in ("lunch", "dinner") and portions:
        if rules.meal_totals(portions)["kcal"] < 0.85 * target:
            # The staple alone can't fill the meal: a bigger helping of the main.
            portions[0].servings = rules.snap(portions[0].food, 1.5, most=2)
            rules.size_meal(portions, target)
        # Even the smallest staple overshoots: drop the salad, then smaller sides,
        # then a smaller main.
        shrink = [p for p in portions if p.food.get("role") == "salad"]
        sides = [p for p in portions[2:] if p.food.get("role") == "main"]
        for p in shrink:
            if rules.meal_totals(portions)["kcal"] > 1.15 * target:
                portions.remove(p)
                rules.size_meal(portions, target)
        for p in [*sides, portions[0]]:
            if rules.meal_totals(portions)["kcal"] > 1.15 * target:
                p.servings = rules.snap(p.food, 0.5)
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
