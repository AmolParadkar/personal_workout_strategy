"""The household grocery list: what this week's meal plans need from a day to
Sunday, added up across everyone (or for one person). Dishes contribute their
recipe ingredients, scaled to the planned servings; simple foods (fruit, eggs,
curd) contribute themselves. Spec: context/pages/nutrition-plan.md ("Weekly
grocery list")."""

from collections import defaultdict
from datetime import date
from typing import Any

from core.models.nutrition import GroceryGroup, GroceryItem, GroceryList, GroceryPerson
from core.nutrition import rules
from core.supabase import SupabaseClient

GROUP_ORDER = [
    "Vegetables", "Leafy greens", "Roots and tubers", "Fruits", "Pulses", "Grains and flours",
    "Bakery", "Dairy", "Eggs", "Meat and fish", "Nuts and seeds", "Oils and fats",
    "Spices and herbs", "Sugar and sweeteners", "Sauces", "Drinks", "Other",
]  # fmt: skip
# Loose measures, in rough grams, so they add up with the rest.
LOOSE_GRAMS = {"sprig": 1, "pinch": 0.3, "drops": 0.1}
# USDA food categories → grocery group, for simple foods planned as themselves.
USDA_GROUPS = {
    "Fruits and Fruit Juices": "Fruits",
    "Vegetables and Vegetable Products": "Vegetables",
    "Legumes and Legume Products": "Pulses",
    "Nut and Seed Products": "Nuts and seeds",
    "Poultry Products": "Meat and fish",
    "Finfish and Shellfish Products": "Meat and fish",
    "Cereal Grains and Pasta": "Grains and flours",
    "Baked Products": "Bakery",
}


def usda_group(food: dict[str, Any]) -> str:
    category = food.get("category") or ""
    if category == "Dairy and Egg Products":
        return "Eggs" if "egg" in food["name"].lower() else "Dairy"
    return USDA_GROUPS.get(category, "Other")


def _amount(value: float, unit: str) -> float | None:
    if unit in ("g", "ml"):
        if value >= 1000:
            return round(value / 1000, 2)
        return round(value / 10) * 10 if value >= 100 else max(round(value), 1)
    if unit in ("nos",):
        return round(value + 0.49)
    return None


def _unit(value: float, unit: str) -> str:
    if unit in ("g", "ml") and value >= 1000:
        return "kg" if unit == "g" else "l"
    return {"nos": ""}.get(unit, unit)


async def grocery_list(
    supabase: SupabaseClient,
    token: str,
    week_start: date,
    from_day: date,
    profile_id: str | None = None,
) -> GroceryList:
    """Everyone in the household (or one person, by `profile_id`)."""
    people = await supabase.select(
        "profiles", {"select": "id,display_name", "order": "created_at"}, token
    )
    if profile_id:
        people = [p for p in people if p["id"] == profile_id]
    plans = await supabase.select(
        "meal_plans",
        {
            "select": "profile_id,planned_meals(day,kind,items)",
            "profile_id": f"in.({','.join(p['id'] for p in people)})" if people else "is.null",
            "week_start": f"eq.{week_start.isoformat()}",
            "status": "eq.active",
        },
        token,
    )
    names = {p["id"]: p.get("display_name") or "Someone" for p in people}
    wanted: list[tuple[str, dict[str, Any]]] = [
        (plan["profile_id"], item)
        for plan in plans
        for meal in plan.get("planned_meals") or []
        if meal["kind"] == "meal" and meal["day"] >= from_day.isoformat()
        for item in meal.get("items") or []
    ]
    ids = {item["food_id"] for _, item in wanted}
    foods = (
        {
            r["id"]: r
            for r in await supabase.select(
                "foods",
                {
                    "select": "id,name,alias,category,basis,serving_g,ingredients",
                    "id": f"in.({','.join(sorted(ids))})",
                },
                token,
            )
        }
        if ids
        else {}
    )

    # (group, name, unit) → amount, and who needs it.
    amounts: dict[tuple[str, str, str], float] = defaultdict(float)
    who: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for owner, item in wanted:
        food = foods.get(item["food_id"])
        if not food:
            continue
        servings = float(item["servings"])
        if food["basis"] == "serving" and food.get("ingredients"):
            for ing in food["ingredients"]:
                unit, amount = ing["unit"], float(ing["amount"])
                if unit in LOOSE_GRAMS:
                    # A sprig of coriander adds to the grams of coriander.
                    unit, amount = "g", amount * LOOSE_GRAMS[unit]
                key = (ing["group"], ing["name"], unit)
                amounts[key] += amount * servings
                who[key].add(names[owner])
        else:
            grams = servings * float(food.get("serving_g") or 100)
            key = (usda_group(food), rules.display_name(food), "g")
            amounts[key] += grams
            who[key].add(names[owner])

    groups: dict[str, list[GroceryItem]] = defaultdict(list)
    for (group, name, unit), value in amounts.items():
        groups[group].append(
            GroceryItem(
                name=name,
                amount=_amount(value, unit),
                unit=_unit(value, unit),
                for_people=sorted(who[(group, name, unit)]),
            )
        )
    ordered = sorted(
        groups.items(),
        key=lambda g: GROUP_ORDER.index(g[0]) if g[0] in GROUP_ORDER else len(GROUP_ORDER),
    )
    with_plan = {plan["profile_id"] for plan in plans}
    return GroceryList(
        week_start=week_start,
        from_day=from_day,
        people=[
            GroceryPerson(profile_id=p["id"], name=names[p["id"]], has_plan=p["id"] in with_plan)
            for p in people
        ],
        groups=[
            GroceryGroup(group=group, items=sorted(items, key=lambda i: i.name.lower()))
            for group, items in ordered
        ],
    )
