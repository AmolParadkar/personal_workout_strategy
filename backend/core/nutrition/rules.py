"""The fixed rules of meal planning: which meals a day has, which foods a person
can have (diet, allergies, dislikes), portion sizes that hit each meal's share of
the day's calories, and nutrient totals worked out from the foods table (never
guessed). Spec: context/pages/nutrition-plan.md."""

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

Food = dict[str, Any]

# --- Meals in a day ------------------------------------------------------------------------

SLOTS_BY_COUNT = {
    1: ["lunch"],
    2: ["lunch", "dinner"],
    3: ["breakfast", "lunch", "dinner"],
    4: ["breakfast", "lunch", "snack", "dinner"],
    5: ["breakfast", "snack", "lunch", "snack", "dinner"],
}
MOST_SLOTS = ["breakfast", "snack", "lunch", "snack", "dinner", "snack"]
SHARE = {"breakfast": 0.25, "lunch": 0.32, "dinner": 0.30, "snack": 0.13}
SLOT_LABELS = {"breakfast": "Breakfast", "lunch": "Lunch", "dinner": "Dinner", "snack": "Snack"}


def slots_for(meals_per_day: int | None) -> list[str]:
    count = meals_per_day or 3
    return SLOTS_BY_COUNT.get(count, MOST_SLOTS) if count < 6 else MOST_SLOTS


def slot_kcal(day_kcal: float, slots: list[str]) -> list[float]:
    """Each meal's share of the day's calories."""
    total = sum(SHARE[s] for s in slots)
    return [day_kcal * SHARE[s] / total for s in slots]


def week_start_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


# --- Who can eat what ---------------------------------------------------------------------

DIETS = {
    "vegetarian": {"vegetarian"},
    "eggetarian": {"vegetarian", "eggetarian"},
    "non_vegetarian": {"vegetarian", "eggetarian", "non_vegetarian"},
}
# Answers that mean "nothing" in the free-text allergy and dislike fields.
NOTHING = {"none", "na", "n/a", "nil", "no", "nothing", "-", "nope", "not applicable"}
# Common allergies and what they're called in recipes.
ALLERGENS = {
    "peanut": ["peanut", "groundnut", "moongfali"],
    "nut": ["almond", "cashew", "walnut", "pistachio", "hazelnut", "pecan", "kaju", "badam",
            "nut"],
    "dairy": ["milk", "curd", "yogurt", "yoghurt", "paneer", "cheese", "butter", "ghee",
              "cream", "khoa", "khoya", "dahi", "lassi", "buttermilk", "whey", "rabri"],
    "gluten": ["wheat", "atta", "maida", "semolina", "suji", "rava", "bread", "flour",
               "chapati", "roti", "paratha", "parantha", "pasta", "noodles", "vermicelli",
               "barley", "rye"],
    "egg": ["egg", "mayonnaise", "omelette", "omlet"],
    "fish": ["fish", "tuna", "salmon", "mackerel", "pomfret", "rohu", "sardine", "anchovy"],
    "shellfish": ["prawn", "shrimp", "crab", "lobster", "squid", "clam", "mussel"],
    "soy": ["soy", "soya", "soyabean", "tofu"],
    "sesame": ["sesame", "til", "gingelly"],
    "capsicum": ["capsicum", "bell pepper", "shimla mirch"],
}  # fmt: skip
ALLERGEN_NAMES = {
    "peanuts": "peanut", "groundnut": "peanut", "nuts": "nut", "tree nut": "nut",
    "tree nuts": "nut", "milk": "dairy", "lactose": "dairy", "wheat": "gluten",
    "eggs": "egg", "seafood": "shellfish", "prawns": "shellfish", "shrimp": "shellfish",
    "soya": "soy", "bell pepper": "capsicum", "bell peppers": "capsicum",
}  # fmt: skip


def avoid_words(allergies: list[str], dislikes: list[str]) -> list[str]:
    """Words that rule a food out, from the person's allergies and dislikes."""
    words: list[str] = []
    for entry in [*allergies, *dislikes]:
        term = entry.strip().lower()
        if not term or term in NOTHING:
            continue
        key = ALLERGEN_NAMES.get(term, term)
        words.extend(ALLERGENS.get(key, [term.removesuffix("s") if len(term) > 3 else term]))
    return sorted(set(words))


def food_text(food: Food) -> str:
    parts = [food.get("name") or "", food.get("alias") or ""]
    parts += [i.get("name") or "" for i in food.get("ingredients") or []]
    return " ".join(parts).lower()


def allowed(food: Food, diet_type: str | None, avoid: list[str]) -> bool:
    if diet_type in DIETS and food["diet"] not in DIETS[diet_type]:
        return False
    if not avoid:
        return True
    text = food_text(food)
    return not any(re.search(rf"\b{re.escape(w)}", text) for w in avoid)


# --- Nutrients and portions ----------------------------------------------------------------

NUTRIENT_KEYS = ("kcal", "protein_g", "carbs_g", "fat_g", "fibre_g")


def factor(food: Food, servings: float) -> float:
    """How many of the food's nutrient units (100 g, or one serving) `servings` is."""
    if food["basis"] == "serving":
        return servings
    return servings * float(food.get("serving_g") or 100) / 100


def nutrients(food: Food, servings: float) -> dict[str, Any]:
    f = factor(food, servings)
    out: dict[str, Any] = {k: float(food.get(k) or 0) * f for k in NUTRIENT_KEYS}
    out["micros"] = {k: float(v) * f for k, v in (food.get("micros") or {}).items()}
    return out


def add(totals: dict[str, Any], more: dict[str, Any]) -> dict[str, Any]:
    out = {k: totals.get(k, 0) + more.get(k, 0) for k in NUTRIENT_KEYS}
    micros = dict(totals.get("micros") or {})
    for k, v in (more.get("micros") or {}).items():
        micros[k] = micros.get(k, 0) + v
    out["micros"] = micros
    return out


def empty() -> dict[str, Any]:
    return {**{k: 0.0 for k in NUTRIENT_KEYS}, "micros": {}}


def rounded(totals: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {k: round(totals.get(k, 0), 1) for k in NUTRIENT_KEYS}
    out["kcal"] = round(totals.get("kcal", 0))
    out["micros"] = {k: round(v, 2) for k, v in (totals.get("micros") or {}).items()}
    return out


def step(food: Food) -> float:
    return 1.0 if food.get("countable") else 0.5


# Most of one food in a meal: pieces (chapatis, eggs, idlis) or bowls and plates.
MOST_PIECES = 4
MOST_PORTIONS = 2


def snap(food: Food, servings: float, most: float | None = None) -> float:
    """Round to a sensible amount: whole pieces, or half servings, within limits."""
    s = step(food)
    limit = most if most is not None else (MOST_PIECES if food.get("countable") else MOST_PORTIONS)
    return min(max(round(servings / s) * s, s), limit)


def display_name(food: Food) -> str:
    return food.get("alias") or food["name"]


def unit_label(food: Food, servings: float) -> str:
    label = food.get("serving_label") or "serving"
    if label.endswith(" g") and food.get("serving_g"):
        return f"{round(servings * float(food['serving_g']))} g"
    amount = f"{servings:g}"
    if servings <= 1 or label.endswith("s"):
        return f"{amount} {label}"
    return f"{amount} {label}{'es' if label.endswith(('ch', 'sh', 'x')) else 's'}"


def item(food: Food, servings: float) -> dict[str, Any]:
    grams = (
        round(servings * float(food["serving_g"]))
        if food["basis"] == "100g" and food.get("serving_g")
        else None
    )
    return {
        "food_id": food["id"],
        "name": display_name(food),
        "servings": servings,
        "unit": unit_label(food, servings),
        "grams": grams,
        "made_with": made_with(food, servings),
    }


# Ingredient groups that say what a dish is made of (not spices or water).
MAIN_GROUPS = {
    "Grains and flours", "Pulses", "Leafy greens", "Vegetables", "Roots and tubers",
    "Fruits", "Dairy", "Eggs", "Meat and fish", "Nuts and seeds", "Oils and fats", "Bakery",
}  # fmt: skip


def made_with(food: Food, servings: float, most: int = 3) -> str | None:
    """A dish's main raw ingredients for the planned amount, so the portion can
    be checked against home cooking, e.g. "about 110 g moong dal, 130 g potato"."""
    parts = [
        i
        for i in food.get("ingredients") or []
        if i.get("unit") in ("g", "ml") and i.get("group") in MAIN_GROUPS
    ]
    totals: dict[tuple[str, str], float] = {}
    for i in parts:
        key = (i["name"], i["unit"])
        totals[key] = totals.get(key, 0) + float(i["amount"]) * servings
    biggest = sorted(totals.items(), key=lambda kv: -kv[1])[:most]
    shown = [
        f"{round(amount / 5) * 5 or 1:g} {unit} {name.lower()}" for (name, unit), amount in biggest
    ]
    return f"Made with about {', '.join(shown)}" if shown else None


@dataclass
class Portion:
    food: Food
    servings: float
    # The item resized to hit the meal's calories (the staple, or the only dish).
    flexible: bool = False


def size_meal(portions: list[Portion], target_kcal: float) -> list[Portion]:
    """Resize the flexible items so the meal lands near its calorie share."""
    fixed = sum(nutrients(p.food, p.servings)["kcal"] for p in portions if not p.flexible)
    flexible = [p for p in portions if p.flexible]
    if not flexible:
        return portions
    room = max(target_kcal - fixed, 0)
    per = sum(nutrients(p.food, 1)["kcal"] for p in flexible) or 1
    for p in flexible:
        p.servings = snap(p.food, room / per)
    return portions


def meal_totals(portions: list[Portion]) -> dict[str, Any]:
    totals = empty()
    for p in portions:
        totals = add(totals, nutrients(p.food, p.servings))
    return totals


def meal_json(slot: str, position: int, portions: list[Portion], note: str | None = None):
    lead = portions[0].food if portions else None
    return {
        "slot": slot,
        "position": position,
        "kind": "meal",
        "name": " + ".join(display_name(p.food) for p in portions)[:200]
        if portions
        else SLOT_LABELS[slot],
        "items": [item(p.food, p.servings) for p in portions],
        "nutrients": rounded(meal_totals(portions)),
        "note": note,
        "_lead": lead["id"] if lead else None,
    }


# --- Protein top-ups ---------------------------------------------------------------------------

# Simple high-protein additions, in order of preference per diet.
PROTEIN_ORDER = {
    "non_vegetarian": ["Grilled chicken breast", "Boiled eggs", "Curd (plain yogurt)",
                       "Greek yogurt (plain)", "Tuna (canned in water)", "Boiled chickpeas"],
    "eggetarian": ["Boiled eggs", "Curd (plain yogurt)", "Greek yogurt (plain)",
                   "Boiled chickpeas", "Tofu (firm)"],
    "vegetarian": ["Greek yogurt (plain)", "Tofu (firm)", "Curd (plain yogurt)",
                   "Boiled chickpeas", "Moong sprouts"],
}  # fmt: skip


def protein_foods(foods: list[Food], diet_type: str | None) -> list[Food]:
    order = PROTEIN_ORDER.get(diet_type or "", PROTEIN_ORDER["eggetarian"])
    by_alias = {f.get("alias"): f for f in foods if f.get("alias")}
    return [by_alias[a] for a in order if a in by_alias]
