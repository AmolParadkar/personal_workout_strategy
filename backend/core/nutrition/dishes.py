"""The household's own dishes: the AI drafts a recipe from a dish's name (raw
ingredients and grams), each ingredient is matched to the USDA ingredient
database, the person checks and edits it, and the nutrients are worked out from
the matched ingredients, never guessed. Saved for the whole household and used by
the meal planner, swaps and the chat. Spec: context/pages/nutrition-plan.md."""

import re
import secrets
from typing import Any

import httpx2
from pydantic import BaseModel

from core.llm import LlmConfig, LlmError, ask_json
from core.models.nutrition import (
    DishDraft,
    DishIngredient,
    DishInput,
    FoodOption,
    IngredientOption,
    Nutrients,
)
from core.nutrition import rules
from core.nutrition.grocery import usda_group
from core.supabase import SupabaseClient

CANDIDATES = 6
INGREDIENT_COLUMNS = (
    "id,name,alias,category,diet,basis,serving_g,kcal,protein_g,carbs_g,fat_g,fibre_g,micros"
)


# Everyday Indian ingredients and their USDA entries, checked before searching
# (most specific first). True: the closest entry there is, not the same food.
COMMON_INGREDIENTS: list[tuple[str, str, bool]] = [
    (r"brown rice", "usda-169703", False),
    (r"\brice\b|chawal", "usda-168877", False),
    (r"maida|all[- ]purpose", "usda-168894", False),
    (r"atta|whole[- ]?wheat flour|wheat flour", "usda-168893", False),
    (r"besan|gram flour|chickpea flour", "usda-174288", False),
    (r"suji|sooji|rava|semolina", "usda-169715", False),
    (r"paneer|cottage cheese", "usda-172223", True),
    (r"ghee|clarified butter", "usda-173412", False),
    (r"peanut butter", "usda-172470", False),
    (r"butter", "usda-173410", False),
    (r"mustard oil", "usda-172337", False),
    (r"\boil\b", "usda-172370", False),
    (r"toor|tuvar|arhar|pigeon pea", "usda-172436", False),
    (r"urad|black gram", "usda-174259", False),
    (r"moong|mung|green gram", "usda-174256", False),
    (r"masoor|lentil", "usda-172420", False),
    (r"chana|chole|chickpea|bengal gram|kabuli", "usda-173756", False),
    (r"rajma|kidney bean", "usda-173744", False),
    (r"jaggery|\bgur\b", "usda-168833", True),
    (r"\bsugar\b", "usda-169655", False),
    (r"green chil+[iy]", "usda-170497", False),
    (r"chil+[iy] powder|red chil+[iy]|kashmiri", "usda-171319", False),
    (r"curd|dahi|yogh?urt", "usda-171284", False),
    (r"\bmilk\b", "usda-171265", False),
    (r"\bcream\b|malai", "usda-170859", False),
    (r"coconut", "usda-170169", False),
    (r"coriander leaves|cilantro|dhania leaves|fresh coriander", "usda-169997", False),
    (r"coriander powder|dhania powder|coriander seed", "usda-170922", False),
    (r"spinach|palak", "usda-168462", False),
    (r"onion", "usda-170000", False),
    (r"tomato", "usda-170457", False),
    (r"potato|\baloo\b", "usda-170026", False),
    (r"ginger|adrak", "usda-169231", False),
    (r"garlic|lahsun", "usda-169230", False),
    (r"\bpeas\b|matar", "usda-170419", False),
    (r"cauliflower|gobi", "usda-169986", False),
    (r"okra|bhindi", "usda-169260", False),
    (r"brinjal|eggplant|baingan", "usda-169228", False),
    (r"cabbage", "usda-169975", False),
    (r"carrot|gajar", "usda-170393", False),
    (r"french beans|green beans", "usda-169961", False),
    (r"\beggs?\b", "usda-171287", False),
    (r"chicken", "usda-171077", False),
    (r"mutton|lamb|keema|goat", "usda-174370", True),
    (r"prawn|shrimp", "usda-175179", False),
    (r"\bfish\b|rohu|surmai|pomfret", "usda-171952", True),
    (r"lauki|bottle gourd|doodhi|ghiya", "usda-169232", False),
    (r"mushroom", "usda-169251", False),
    (r"turmeric|haldi", "usda-172231", False),
    (r"cumin|jeera", "usda-170923", False),
    (r"fenugreek seed|methi seed", "usda-171324", False),
    (r"cashew|kaju", "usda-170162", False),
    (r"peanut|groundnut", "usda-172430", False),
    (r"lemon|lime", "usda-167747", False),
    (r"soya|soybean", "usda-174270", False),
]
COMMON = [(re.compile(p, re.IGNORECASE), f, a) for p, f, a in COMMON_INGREDIENTS]


def common_match(name: str) -> tuple[str, bool] | None:
    return next(((f, a) for p, f, a in COMMON if p.search(name)), None)


class DishError(Exception):
    """A dish that can't be saved, with a message for the person."""


class LlmIngredient(BaseModel):
    name: str
    grams: float
    # How the USDA database would name it, e.g. "Mung beans, mature seeds, raw".
    search: str = ""


class LlmRecipe(BaseModel):
    name: str
    serves: int
    role: str
    ingredients: list[LlmIngredient]


class LlmMatch(BaseModel):
    i: int
    # A candidate's letter, or empty for none.
    pick: str | None = None
    approximate: bool = False


class LlmMatches(BaseModel):
    matches: list[LlmMatch]


RECIPE_SYSTEM = (
    "You are a home cook and dietitian. You write realistic home recipes with raw "
    "ingredient weights. Answer with JSON only."
)
MATCH_SYSTEM = (
    "You match recipe ingredients to entries in the USDA food database. Answer with JSON only."
)


def recipe_prompt(name: str, note: str | None) -> str:
    extra = f"\nWhat they said about it: {note.strip()}" if note and note.strip() else ""
    return f"""Write a typical home recipe for "{name}" (Indian home style unless the name
says otherwise).{extra}

Give every ingredient's RAW weight in grams for the whole recipe (dry dal or rice,
not cooked; oil and ghee included), how many servings it makes, and its role:
breakfast, main (a curry, dal, sabzi, meat or egg dish), staple (roti, rice, paratha),
salad (salads and raitas) or snack. Leave out water and salt. For each ingredient
add how the USDA FoodData Central database names it, e.g. "Mung beans, mature seeds,
raw", "Wheat flour, whole-grain", "Oil, vegetable, soybean", "Onions, raw".

Return JSON: {{"name": "{name}", "serves": 2, "role": "main",
"ingredients": [{{"name": "Moong dal", "grams": 100,
  "search": "Mung beans, mature seeds, raw"}}]}}"""


async def _search(supabase: SupabaseClient, token: str, query: str) -> list[dict[str, Any]]:
    """USDA ingredients matching `query`: every word, then fewer words, then the
    closest names."""
    query = query.strip()
    tries = [query, query.split(",")[0], " ".join(query.split()[:2])]
    for q in dict.fromkeys(t for t in tries if len(t) >= 2):
        rows = await supabase.rpc(
            "search_foods",
            {"p_query": q.replace(",", " "), "p_kind": "ingredient", "p_limit": CANDIDATES},
            token,
        )
        if rows:
            return rows
    return (
        await supabase.rpc(
            "suggest_foods",
            {"p_query": query, "p_kind": "ingredient", "p_limit": CANDIDATES},
            token,
        )
        or []
    )


def match_prompt(recipe: LlmRecipe, candidates: dict[int, list[dict[str, Any]]]) -> str:
    blocks = []
    for n, options in candidates.items():
        ingredient = recipe.ingredients[n]
        lines = (
            "\n".join(f"  {chr(97 + k)}. {o['name']}" for k, o in enumerate(options))
            or "  (none found)"
        )
        blocks.append(f"{n}. {ingredient.name}:\n{lines}")
    return f"""Recipe: {recipe.name}. For each ingredient, pick the database entry that
matches it (raw, not cooked, unless the ingredient is cooked). If none is the same food,
pick the closest similar one and mark it approximate (e.g. paneer → a fresh cheese);
if nothing is close, leave pick empty.

{chr(10).join(blocks)}

Return JSON: {{"matches": [{{"i": 0, "pick": "a", "approximate": false}}]}}"""


def _per_100g(food: dict[str, Any], grams: float) -> dict[str, Any]:
    f = grams / 100
    out: dict[str, Any] = {k: float(food.get(k) or 0) * f for k in rules.NUTRIENT_KEYS}
    out["micros"] = {k: float(v) * f for k, v in (food.get("micros") or {}).items()}
    return out


def compute(
    name: str,
    role: str,
    serves: int,
    ingredients: list[DishIngredient],
    foods: dict[str, dict[str, Any]],
) -> DishDraft:
    """Nutrients for one serving from the matched ingredients."""
    total = rules.empty()
    out = []
    diets = set()
    for i in ingredients:
        food = foods.get(i.food_id or "")
        if food:
            n = _per_100g(food, i.grams)
            total = rules.add(total, n)
            diets.add(food["diet"])
            out.append(
                i.model_copy(
                    update={
                        "food_name": food["name"],
                        "kcal": round(n["kcal"]),
                        "protein_g": round(n["protein_g"], 1),
                    }
                )
            )
        else:
            out.append(i.model_copy(update={"food_id": None, "food_name": None, "kcal": 0}))
        if rules.MEAT_WORDS.search(i.name):
            diets.add("non_vegetarian")
    per_serving = rules.rounded(
        {
            **{k: v / serves for k, v in total.items() if k != "micros"},
            "micros": {k: v / serves for k, v in total["micros"].items()},
        }
    )
    diet = (
        "non_vegetarian"
        if "non_vegetarian" in diets
        else "eggetarian"
        if "eggetarian" in diets
        else "vegetarian"
    )
    return DishDraft(
        name=name.strip(),
        role=role if role in ("breakfast", "main", "staple", "salad", "snack") else "main",
        serves=serves,
        diet=diet,
        ingredients=out,
        per_serving=Nutrients(**per_serving),
        unmatched=[i.name for i in out if not i.food_id],
    )


async def _foods(supabase: SupabaseClient, token: str, ids: set[str]) -> dict[str, dict]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    rows = await supabase.select(
        "foods",
        {"select": INGREDIENT_COLUMNS, "id": f"in.({','.join(sorted(ids))})", "source": "eq.usda"},
        token,
    )
    return {r["id"]: r for r in rows}


async def draft(
    supabase: SupabaseClient,
    http: httpx2.AsyncClient,
    llm: LlmConfig | None,
    token: str,
    name: str,
    note: str | None,
) -> DishDraft:
    """The AI's recipe for a dish, matched to the ingredient database (to check
    and edit before saving)."""
    if llm is None:
        raise LlmError("No LLM set up")
    recipe = (
        await ask_json(http, llm, RECIPE_SYSTEM, recipe_prompt(name, note), LlmRecipe, 700)
    ).value
    recipe.ingredients = [i for i in recipe.ingredients if i.grams > 0][:25]
    if not recipe.ingredients:
        raise LlmError("No ingredients")
    # Everyday ingredients from the fixed list; the rest searched and matched by the AI.
    known = {n: common_match(i.name) for n, i in enumerate(recipe.ingredients)}
    common_foods = await _foods(supabase, token, {m[0] for m in known.values() if m})
    chosen: dict[int, tuple[dict[str, Any], bool]] = {
        n: (common_foods[m[0]], m[1]) for n, m in known.items() if m and m[0] in common_foods
    }
    rest = [n for n in range(len(recipe.ingredients)) if n not in chosen]
    candidates = {}
    for n in rest:
        ingredient = recipe.ingredients[n]
        candidates[n] = await _search(supabase, token, ingredient.search or ingredient.name)
    if rest:
        try:
            picks = (
                await ask_json(
                    http, llm, MATCH_SYSTEM, match_prompt(recipe, candidates), LlmMatches, 400
                )
            ).value.matches
        except LlmError:
            # The closest name, marked as approximate for the person to check.
            picks = [LlmMatch(i=n, pick="a", approximate=True) for n in rest]
        for p in picks:
            options = candidates.get(p.i) or []
            k = ord(p.pick[0].lower()) - 97 if p.pick else -1
            if 0 <= k < len(options):
                chosen[p.i] = (options[k], p.approximate)
    ingredients = [
        DishIngredient(
            name=i.name[:80],
            grams=round(min(max(i.grams, 0.5), 5000), 1),
            food_id=chosen[n][0]["id"] if n in chosen else None,
            approximate=chosen[n][1] if n in chosen else False,
        )
        for n, i in enumerate(recipe.ingredients)
    ]
    foods = {f["id"]: f for f, _ in chosen.values()}
    return compute(
        recipe.name or name, recipe.role, max(1, min(recipe.serves, 20)), ingredients, foods
    )


async def preview(supabase: SupabaseClient, token: str, dish: DishInput) -> DishDraft:
    """The numbers again after the person edits the recipe."""
    foods = await _foods(supabase, token, {i.food_id or "" for i in dish.ingredients})
    return compute(dish.name, dish.role, dish.serves, dish.ingredients, foods)


async def save(
    supabase: SupabaseClient, token: str, profile_id: str, dish: DishInput
) -> FoodOption:
    foods = await _foods(supabase, token, {i.food_id or "" for i in dish.ingredients})
    result = compute(dish.name, dish.role, dish.serves, dish.ingredients, foods)
    matched = [i for i in result.ingredients if i.food_id]
    if not matched:
        raise DishError("Match at least one ingredient so the nutrients can be worked out.")
    if not 20 <= result.per_serving.kcal <= 1500:
        raise DishError(
            f"One serving comes to {result.per_serving.kcal:.0f} kcal. Check the grams and "
            "the number of servings."
        )
    household = (
        await supabase.select(
            "profiles", {"select": "household_id", "id": f"eq.{profile_id}"}, token
        )
    )[0]["household_id"]
    n = result.per_serving
    row = {
        "id": f"custom-{secrets.token_hex(8)}",
        "name": result.name,
        "source": "custom",
        "category": result.role,
        "role": result.role,
        "diet": result.diet,
        "basis": "serving",
        "serving_label": "serving",
        "countable": False,
        "kcal": n.kcal,
        "protein_g": n.protein_g,
        "carbs_g": n.carbs_g,
        "fat_g": n.fat_g,
        "fibre_g": n.fibre_g,
        "micros": n.micros,
        "ingredients": [
            {
                "code": i.food_id,
                "name": i.name,
                "amount": round(i.grams / result.serves, 1),
                "unit": "g",
                "group": usda_group(foods[i.food_id]),
            }
            for i in matched
        ],
        "household_id": household,
        "created_by": profile_id,
    }
    await supabase.insert("foods", row, token, returning="id")
    return FoodOption(
        id=row["id"],
        name=row["name"],
        serving_label="serving",
        kcal=round(n.kcal),
        protein_g=round(n.protein_g, 1),
        diet=row["diet"],
        custom=True,
    )


async def household_dishes(supabase: SupabaseClient, token: str) -> list[FoodOption]:
    rows = await supabase.select(
        "foods",
        {
            "select": "id,name,serving_label,kcal,protein_g,diet",
            "source": "eq.custom",
            "order": "name",
        },
        token,
    )
    return [
        FoodOption(
            id=r["id"],
            name=r["name"],
            serving_label=r.get("serving_label"),
            kcal=round(float(r["kcal"])),
            protein_g=round(float(r["protein_g"]), 1),
            diet=r["diet"],
            custom=True,
        )
        for r in rows
    ]


async def remove(supabase: SupabaseClient, token: str, profile_id: str, dish_id: str) -> None:
    await supabase.delete(
        "foods",
        {"id": f"eq.{dish_id}", "source": "eq.custom", "created_by": f"eq.{profile_id}"},
        token,
    )


async def search_ingredients(
    supabase: SupabaseClient, token: str, query: str
) -> list[IngredientOption]:
    rows = await _search(supabase, token, query) if len(query.strip()) >= 2 else []
    return [
        IngredientOption(
            id=r["id"],
            name=r["name"],
            kcal=round(float(r["kcal"])),
            protein_g=round(float(r["protein_g"]), 1),
        )
        for r in rows
    ]
