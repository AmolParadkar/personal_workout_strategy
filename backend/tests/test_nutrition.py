"""Meal plans (M7 part 1): targets, the planning rules, the LLM's choices, making a
plan on Vercel or the Mac worker, swaps, eating out and the grocery list."""

import asyncio
import json
from datetime import date

import httpx2
import pytest

from core.llm import LlmConfig, LlmError
from core.nutrition import generate, grocery, plans, rules
from core.nutrition.generate import MealInputs
from core.nutrition.targets import Body, daily_targets


def food(
    id,
    name,
    role,
    kcal,
    protein,
    carbs=None,
    fat=None,
    diet="vegetarian",
    basis="serving",
    label="bowl",
    grams=None,
    countable=False,
    alias=None,
    ingredients=None,
    category=None,
):
    carbs = carbs if carbs is not None else max((kcal - 4 * protein) * 0.6 / 4, 0)
    fat = fat if fat is not None else max((kcal - 4 * protein - 4 * carbs) / 9, 0)
    return {
        "id": id,
        "name": name,
        "alias": alias,
        "role": role,
        "diet": diet,
        "basis": basis,
        "serving_label": label,
        "serving_g": grams,
        "countable": countable,
        "kcal": kcal,
        "protein_g": protein,
        "carbs_g": carbs,
        "fat_g": fat,
        "fibre_g": 3,
        "micros": {"iron_mg": 1.0},
        "ingredients": ingredients or [],
        "category": category,
    }


FOODS = [
    food("indb-B1", "Poha", "breakfast", 250, 6),
    food("indb-B2", "Moong dal cheela", "breakfast", 120, 7, label="cheela", countable=True),
    food("indb-B3", "Masala omelette", "breakfast", 180, 12, diet="eggetarian", label="omelette",
         countable=True),
    food("indb-M1", "Rajma curry", "main", 220, 11,
         ingredients=[{"code": "B020", "name": "Rajmah", "amount": 40, "unit": "g",
                       "group": "Pulses"},
                      {"code": "G017", "name": "Onion", "amount": 30, "unit": "g",
                       "group": "Vegetables"}]),
    food("indb-M2", "Palak paneer", "main", 300, 15),
    food("indb-M3", "Chicken curry", "main", 280, 25, diet="non_vegetarian"),
    food("indb-M4", "Capsicum masala", "main", 150, 4,
         ingredients=[{"code": "D010", "name": "Capsicum", "amount": 80, "unit": "g",
                       "group": "Vegetables"}]),
    food("indb-M5", "Moong dal", "main", 140, 8),
    food("indb-M6", "Butter-heavy korma", "main", 400, 5, carbs=10, fat=40),
    food("indb-S1", "Chapati/Roti", "staple", 73, 2, label="chapati", countable=True,
         ingredients=[{"code": "A019", "name": "Atta", "amount": 25, "unit": "g",
                       "group": "Grains and flours"}]),
    food("indb-S2", "Boiled rice (Uble chawal)", "staple", 350, 8, label="plate"),
    food("indb-X1", "Cucumber raita", "salad", 90, 4),
    food("usda-1", "Bananas, raw", "fruit", 89, 1.1, basis="100g", label="banana", grams=118,
         countable=True, alias="Banana", category="Fruits and Fruit Juices"),
    food("usda-2", "Yogurt, plain", "protein", 61, 3.5, basis="100g", label="bowl", grams=150,
         alias="Curd (plain yogurt)", category="Dairy and Egg Products"),
    food("usda-3", "Egg, hard-boiled", "protein", 155, 12.6, basis="100g", label="egg", grams=50,
         countable=True, alias="Boiled eggs", diet="eggetarian",
         category="Dairy and Egg Products"),
    food("usda-4", "Chicken breast, roasted", "protein", 165, 31, basis="100g", label="100 g",
         grams=100, alias="Grilled chicken breast", diet="non_vegetarian",
         category="Poultry Products"),
    food("usda-5", "Almonds", "snack", 579, 21, basis="100g", label="handful", grams=25,
         alias="Almonds", carbs=22, fat=50, category="Nut and Seed Products"),
]  # fmt: skip


def inputs(**overrides) -> MealInputs:
    values = {
        "profile_id": "p1",
        "week_start": date(2026, 10, 19),
        "today": date(2026, 10, 19),
        "body": Body(70, 172, 35, "male", ["build_muscle"]),
        "diet_type": "non_vegetarian",
        "cuisines": ["Indian"],
        "allergies": [],
        "dislikes": [],
        "meals_per_day": 4,
        "cooking_minutes": 30,
        "training": {date(2026, 10, 19): 60, date(2026, 10, 21): 45},
        "foods": FOODS,
    }
    values.update(overrides)
    return MealInputs(**values)


def run(coroutine):
    return asyncio.run(coroutine)


# --- Targets ----------------------------------------------------------------------------------


def test_training_days_get_more_calories_mostly_as_carbs():
    body = Body(70, 172, 35, "male", ["general_health"])
    rest, trained = daily_targets(body), daily_targets(body, 60)
    assert trained.kcal - rest.kcal == pytest.approx(280, abs=10)
    assert trained.protein_g == rest.protein_g and trained.carbs_g > rest.carbs_g
    assert "60-minute session" in trained.reasons["kcal"]
    assert "rest day" in rest.reasons["kcal"]


def test_goals_change_calories_and_protein():
    base = Body(80, 175, 38, "male", [])
    maintain = daily_targets(base)
    lose = daily_targets(Body(80, 175, 38, "male", ["lose_fat"]))
    recomp = daily_targets(Body(80, 175, 38, "male", ["lose_fat", "build_muscle"]))
    assert lose.kcal < recomp.kcal < maintain.kcal
    assert lose.protein_g == 128 and maintain.protein_g == 96  # 1.6 and 1.2 g/kg
    assert "lose fat" in lose.reasons["kcal"]


def test_never_below_a_safe_minimum_and_protein_from_a_healthy_weight():
    small = daily_targets(Body(45, 150, 60, "female", ["lose_fat"]))
    assert small.kcal >= 1200
    heavy = daily_targets(Body(130, 170, 40, "male", ["lose_fat"]))
    assert heavy.protein_g == round(1.6 * 27 * 1.7**2)  # weight at a BMI of 27


def test_steps_raise_everyday_activity_and_micros_follow_sex():
    sitting = daily_targets(Body(60, 165, 30, "female", [], avg_steps=3000))
    active = daily_targets(Body(60, 165, 30, "female", [], avg_steps=12000))
    assert active.kcal > sitting.kcal and "12,000 steps" in active.reasons["kcal"]
    assert sitting.micros["iron_mg"] == 18
    assert daily_targets(Body(60, 165, 30, "male", [])).micros["iron_mg"] == 8


# --- Rules -----------------------------------------------------------------------------------


def test_meals_per_day_sets_the_meals_and_their_shares():
    assert rules.slots_for(3) == ["breakfast", "lunch", "dinner"]
    assert rules.slots_for(5).count("snack") == 2 and len(rules.slots_for(8)) == 6
    shares = rules.slot_kcal(2000, rules.slots_for(4))
    assert sum(shares) == pytest.approx(2000) and shares[1] > shares[2] > shares[0] / 2


def test_allergies_and_dislikes_rule_out_foods_by_name_and_ingredient():
    avoid = rules.avoid_words(["Capsicum", "None"], ["NA", "peanuts"])
    assert "capsicum" in avoid and "shimla mirch" in avoid and "groundnut" in avoid
    assert "none" not in avoid
    capsicum, rajma = FOODS[6], FOODS[3]
    assert not rules.allowed(capsicum, "vegetarian", avoid)
    assert rules.allowed(rajma, "vegetarian", avoid)
    assert not rules.allowed(FOODS[5], "vegetarian", [])  # chicken
    assert not rules.allowed(FOODS[2], "vegetarian", []) and rules.allowed(
        FOODS[2], "eggetarian", []
    )


def test_portions_are_whole_pieces_or_half_bowls_within_limits():
    chapati, rice = FOODS[9], FOODS[10]
    assert rules.snap(chapati, 2.4) == 2 and rules.snap(chapati, 9) == 4
    assert rules.snap(rice, 0.8) == 1 and rules.snap(rice, 0.2) == 0.5 and rules.snap(rice, 5) == 2
    assert rules.unit_label(chapati, 3) == "3 chapatis"
    assert rules.unit_label(FOODS[15], 1.5) == "150 g"
    assert rules.unit_label(FOODS[12], 1) == "1 banana"


def test_nutrients_come_from_the_foods_table():
    banana = FOODS[12]  # 89 kcal per 100 g, 118 g each
    assert rules.nutrients(banana, 2)["kcal"] == pytest.approx(89 * 2.36)
    assert rules.nutrients(FOODS[3], 1.5)["protein_g"] == pytest.approx(16.5)


# --- A rules-only week ----------------------------------------------------------------------------


def day_totals(day):
    return {k: sum(m["nutrients"][k] for m in day["meals"]) for k in ("kcal", "protein_g", "fat_g")}


def test_rules_only_week_lands_near_the_targets():
    plan = run(generate.build_plan(inputs(), None, None, "new_week"))
    assert plan["made_by"] == "rules" and len(plan["days"]) == 7
    for day in plan["days"]:
        target, got = day["targets"], day_totals(day)
        assert abs(got["kcal"] - target["kcal"]) / target["kcal"] < 0.25, day["day"]
        assert [m["slot"] for m in day["meals"]] == ["breakfast", "lunch", "snack", "dinner"]
    first = plan["days"][0]
    lunch = first["meals"][1]
    assert lunch["items"][1]["name"] in ("Chapati/Roti", "Boiled rice (Uble chawal)")
    assert first["targets"]["training_minutes"] == 60
    assert "training days" in plan["rationale"]


def test_mains_vary_and_fatty_dishes_are_left_out():
    plan = run(generate.build_plan(inputs(), None, None, "new_week"))
    mains = [m["items"][0]["food_id"] for d in plan["days"] for m in d["meals"][1::2]]
    assert "indb-M6" not in mains
    for a, b in zip(mains, mains[1:], strict=False):
        assert a != b


def test_short_protein_is_topped_up_with_simple_foods_for_the_diet():
    veg = run(generate.build_plan(inputs(diet_type="vegetarian"), None, None, "new_week"))
    added = [i["name"] for d in veg["days"] for m in d["meals"] for i in m["items"]]
    assert "Grilled chicken breast" not in added and "Boiled eggs" not in added
    notes = [m["note"] for d in veg["days"] for m in d["meals"] if m["note"]]
    assert notes and all("protein target" in n for n in notes)


def test_days_already_past_are_not_planned():
    plan = run(generate.build_plan(inputs(today=date(2026, 10, 23)), None, None, "new_week"))
    assert [d["day"] for d in plan["days"]] == [
        "2026-10-23", "2026-10-24", "2026-10-25",
    ]  # fmt: skip


# --- The LLM's choices ---------------------------------------------------------------------------

GROQ = LlmConfig("gsk_test", "qwen/test", None, "")


def answering(fn):
    def handler(request):
        prompt = json.loads(request.content)["messages"][1]["content"]
        return httpx2.Response(
            200, json={"choices": [{"message": {"content": json.dumps(fn(prompt))}}]}
        )

    return httpx2.AsyncClient(transport=httpx2.MockTransport(handler))


def codes_in(prompt, kind):
    return [
        line.split(" ")[0]
        for line in prompt.splitlines()
        if line[:1] == kind and line[1:2].isdigit()
    ]


def test_valid_llm_choices_are_used_and_bad_ones_fall_back():
    def answer(prompt):
        b, m, s, n = (codes_in(prompt, k) for k in "bmsn")
        good = [[b[0]], [m[0], s[0]], [n[0]], [m[1], s[0]]]
        bad = [["z9"], [m[0]], [b[0]], [m[2], s[0], s[0], s[0]]]
        return {"note": "Simple home food.", "days": {"2026-10-19": good, "2026-10-20": bad}}

    async def go():
        async with answering(answer) as http:
            return await generate.build_plan(inputs(), http, GROQ, "requested")

    plan = run(go())
    assert plan["made_by"] == "groq:qwen/test" and plan["rationale"].startswith("Simple home")
    assert all(len(m["items"]) >= 1 for d in plan["days"] for m in d["meals"])


def test_the_prompt_lists_only_foods_the_person_can_have():
    c = generate.candidates(inputs(diet_type="vegetarian", allergies=["capsicum"]))
    prompt = generate.build_prompt(inputs(), c, generate.week_targets(inputs()))
    assert "Chicken curry" not in prompt and "Capsicum masala" not in prompt
    assert "Rajma curry" in prompt and "training 60 min" in prompt


def test_without_an_answer_the_api_can_hand_over_to_the_worker():
    async def go():
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(lambda r: httpx2.Response(503))
        ) as http:
            await generate.build_plan(
                inputs(), http, GROQ, "requested", rules_only_if_llm_fails=False
            )

    with pytest.raises(LlmError):
        run(go())


# --- Making a plan: Vercel first, then the Mac worker --------------------------------------------


class FakeSupabase:
    def __init__(self, active=False, weight=70.0):
        self.active = active
        self.weight = weight
        self.saved = []
        self.queued = []
        self.updated = []
        self.meals = []

    def plan_row(self, status):
        return {
            "id": "plan",
            "week_start": "2026-10-19",
            "status": status,
            "rationale": "Week.",
            "made_by": "rules",
            "reason": "new_week",
            "change_note": None,
            "created_at": "2026-10-19T08:00:00Z",
            "daily_targets": [],
            "planned_meals": [],
        }

    async def select(self, table, params, token=None):
        if table == "meal_plans":
            if params.get("week_start") == "eq.2026-10-12":
                return []
            if self.saved:
                return [self.plan_row(self.saved[-1]["p_status"])]
            return [self.plan_row("active")] if self.active else []
        if table == "jobs":
            return [{"id": "j"}] if self.queued else []
        if table == "profiles":
            return [
                {
                    "sex": "male",
                    "date_of_birth": "1990-01-01",
                    "height_cm": 175,
                    "goals": ["build_muscle"],
                }
            ]
        if table == "health_samples":
            if params.get("metric") == "eq.weight_kg":
                return [{"value": self.weight}] if self.weight else []
            return []
        if table == "diet_preferences":
            return [
                {
                    "diet_type": "vegetarian",
                    "cuisines": ["Indian"],
                    "allergies": [],
                    "dislikes": [],
                    "meals_per_day": 3,
                    "cooking_minutes": 30,
                }
            ]
        if table == "workout_plans":
            return [{"workout_sessions": [{"day": "2026-10-19", "minutes": 45}]}]
        if table == "foods":
            return FOODS
        raise AssertionError(table)

    async def rpc(self, function, args, token=None):
        assert function == "save_meal_plan"
        self.saved.append(args)
        return "plan"

    async def insert(self, table, values, token, returning="*"):
        self.queued.append(values)
        return [{"id": "j", "status": "pending", "attempts": 0, **values}]


def answer_for_whatever(request):
    prompt = json.loads(request.content)["messages"][1]["content"]
    b, m, s = (codes_in(prompt, k) for k in "bms")
    days = sorted({line[:10] for line in prompt.splitlines() if line[:4] == "2026"})
    week = {"note": "Varied.", "days": {d: [[b[0]], [m[0], s[0]], [m[1], s[0]]] for d in days}}
    return httpx2.Response(200, json={"choices": [{"message": {"content": json.dumps(week)}}]})


def generate_with(supabase, handler, llm=GROQ, reason="requested"):
    async def go():
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as http:
            return await plans.generate(supabase, http, llm, "t", "p1", date(2026, 10, 19), reason)

    return run(go())


def test_first_plan_is_made_straight_away_and_active():
    supabase = FakeSupabase()
    week = generate_with(supabase, answer_for_whatever)
    [saved] = supabase.saved
    assert saved["p_status"] == "active" and saved["p_plan"]["made_by"] == "groq:qwen/test"
    first = saved["p_plan"]["days"][0]
    assert first["targets"]["training_minutes"] == 45 and len(first["meals"]) == 3
    assert week.active is not None and not supabase.queued


def test_a_new_plan_when_one_exists_is_a_draft():
    supabase = FakeSupabase(active=True)
    generate_with(supabase, answer_for_whatever)
    assert supabase.saved[0]["p_status"] == "draft"


def test_no_weigh_in_means_no_plan_yet_but_says_what_is_missing():
    supabase = FakeSupabase(weight=None)
    week = generate_with(supabase, answer_for_whatever)
    assert week.missing == ["weight"] and not supabase.saved and not supabase.queued


def test_failing_llm_hands_the_plan_to_the_mac_worker():
    supabase = FakeSupabase()
    week = generate_with(supabase, lambda r: httpx2.Response(503))
    [job] = supabase.queued
    assert job["type"] == "generate_meal_plan" and job["payload"]["status"] == "active"
    assert week.generating and not supabase.saved


def test_worker_job_saves_a_plan_without_an_llm():
    from core.jobs import JobContext, meal_plan

    class Db:
        def __init__(self):
            self.fake = FakeSupabase()

        async def select(self, table, params):
            return await self.fake.select(table, params)

        async def update(self, *args, **kwargs):
            return []

        async def rpc(self, function, args):
            return await self.fake.rpc(function, args)

    db = Db()
    result = run(
        meal_plan.run(
            {
                "profile_id": "p1",
                "week_start": "2026-10-19",
                "today": "2026-10-19",
                "status": "active",
                "reason": "new_week",
            },
            JobContext(worker_id="mac", attempt=1, http=None, llm=None, db=db),
        )
    )
    assert result["made_by"] == "rules" and db.fake.saved[0]["p_status"] == "active"


# --- Eating out and the grocery list -------------------------------------------------------------


def saved_week():
    """A saved plan as the database returns it (ids added)."""
    plan = run(generate.build_plan(inputs(meals_per_day=3), None, None, "new_week"))
    targets, meals = [], []
    for d in plan["days"]:
        targets.append({"day": d["day"], **d["targets"]})
        for m in d["meals"]:
            meals.append({"id": f"{d['day']}-{m['position']}", "day": d["day"], **m})
    return {
        "id": "plan",
        "week_start": "2026-10-19",
        "status": "active",
        "rationale": "Week.",
        "made_by": "rules",
        "reason": "new_week",
        "change_note": None,
        "created_at": "2026-10-19T08:00:00Z",
        "daily_targets": targets,
        "planned_meals": meals,
    }


class PlanSupabase:
    def __init__(self):
        self.row = saved_week()
        self.saved = []

    async def select(self, table, params, token=None):
        if table == "meal_plans" and params.get("status") == "eq.active":
            return [self.row]
        if table == "meal_plans" and params.get("status") == "in.(active,draft)":
            draft = [{**self.row, "status": "draft", **self.saved[-1]["p_plan"]}]
            return [self.row] + (draft if self.saved else [])
        if table == "meal_plans":
            return (
                [{**self.row, "status": "draft", **self.saved[-1]["p_plan"]}] if self.saved else []
            )
        if table == "foods":
            return FOODS
        if table == "jobs":
            return []
        if table == "profiles":
            return [{"id": "p1", "display_name": "Amol"}, {"id": "p2", "display_name": "Sam"}]
        raise AssertionError(table)

    async def rpc(self, function, args, token=None):
        self.saved.append(args)
        return "draft"


def test_eating_out_previews_a_rebalanced_week():
    supabase = PlanSupabase()
    dinner = "2026-10-21-2"
    before = {m["day"]: m for m in supabase.row["planned_meals"] if m["position"] == 1}
    run(plans.eating_out(supabase, "t", "p1", [dinner], date(2026, 10, 19)))
    [draft] = supabase.saved
    assert draft["p_status"] == "draft" and draft["p_plan"]["change_note"].startswith("Eating out")
    days = {d["day"]: d for d in draft["p_plan"]["days"]}
    out = days["2026-10-21"]["meals"][2]
    assert out["kind"] == "eating_out" and out["items"] == [] and out["nutrients"]["kcal"] > 0
    later = sum(
        sum(m["nutrients"]["kcal"] for m in days[d]["meals"]) for d in days if d > "2026-10-21"
    )
    before_later = sum(
        sum(m["nutrients"]["kcal"] for m in supabase.row["planned_meals"] if m["day"] == d)
        for d in days
        if d > "2026-10-21"
    )
    assert later < before_later  # trimmed to make up for it
    assert days["2026-10-20"]["meals"][1]["items"] == before["2026-10-20"]["items"]


def test_eating_out_only_for_this_weeks_upcoming_meals():
    supabase = PlanSupabase()
    with pytest.raises(plans.ChangeError):
        run(plans.eating_out(supabase, "t", "p1", ["2026-10-19-1"], date(2026, 10, 20)))
    with pytest.raises(plans.ChangeError):
        run(plans.eating_out(supabase, "t", "p1", ["nope"], date(2026, 10, 19)))


def test_grocery_list_adds_up_ingredients_across_the_household():
    class GrocerySupabase:
        async def select(self, table, params, token=None):
            if table == "profiles":
                return [{"id": "p1", "display_name": "Amol"}, {"id": "p2", "display_name": "Sam"}]
            if table == "meal_plans":
                meal = {
                    "day": "2026-10-20",
                    "kind": "meal",
                    "items": [
                        {"food_id": "indb-M1", "servings": 1.5},
                        {"food_id": "indb-S1", "servings": 2},
                    ],
                }
                snack = {"day": "2026-10-20", "kind": "meal", "items": [
                    {"food_id": "usda-1", "servings": 1}]}  # fmt: skip
                past = {"day": "2026-10-19", "kind": "meal", "items": [
                    {"food_id": "indb-M1", "servings": 10}]}  # fmt: skip
                return [
                    {"profile_id": "p1", "planned_meals": [meal, snack, past]},
                    {"profile_id": "p2", "planned_meals": [meal]},
                ]
            if table == "foods":
                return FOODS
            raise AssertionError(table)

    result = run(
        grocery.grocery_list(GrocerySupabase(), "t", date(2026, 10, 19), date(2026, 10, 20))
    )
    items = {i.name: i for g in result.groups for i in g.items}
    assert items["Rajmah"].amount == 120 and items["Rajmah"].unit == "g"  # 40 g x 1.5 x 2
    assert items["Atta"].amount == 100 and items["Atta"].for_people == ["Amol", "Sam"]
    assert items["Banana"].amount == 120 and items["Banana"].for_people == ["Amol"]
    assert [g.group for g in result.groups][:2] == ["Vegetables", "Fruits"]
    assert all(p.has_plan for p in result.people)


def test_dishes_too_big_for_a_small_persons_meals_are_left_out():
    dosa = food("indb-B9", "Masala dosa", "breakfast", 450, 9, label="dosa", countable=True)
    small = inputs(body=Body(48, 152, 55, "female", ["lose_fat"]), foods=[*FOODS, dosa])
    big = inputs(body=Body(95, 185, 30, "male", ["build_muscle"]), foods=[*FOODS, dosa])
    assert dosa not in generate.candidates(small).by_kind["b"]
    assert dosa in generate.candidates(big).by_kind["b"]


def test_protein_add_ons_keep_each_meal_near_its_share():
    plan = run(
        generate.build_plan(
            inputs(body=Body(48, 152, 55, "female", ["lose_fat"]), meals_per_day=5),
            None,
            None,
            "new_week",
        )
    )
    for day in plan["days"]:
        shares = rules.slot_kcal(day["targets"]["kcal"], rules.slots_for(5))
        for meal, share in zip(day["meals"], shares, strict=True):
            if meal["note"]:
                assert meal["nutrients"]["kcal"] <= generate.MEAL_OVER * share + 1


def test_dishes_say_what_the_portion_is_made_of():
    rajma = rules.item(FOODS[3], 1.5)
    assert rajma["made_with"] == "Made with about 60 g rajmah, 45 g onion"
    assert rules.item(FOODS[12], 1)["made_with"] is None  # a banana is just a banana


# --- Your own dishes and the chat -------------------------------------------------------------

from core.models.nutrition import DishIngredient  # noqa: E402
from core.nutrition import chat, dishes  # noqa: E402


def test_everyday_ingredients_match_their_usda_entries():
    assert dishes.common_match("Atta") == ("usda-168893", False)
    assert dishes.common_match("Paneer") == ("usda-172223", True)  # closest: queso fresco
    assert dishes.common_match("Peanut butter")[0] == "usda-172470"
    assert dishes.common_match("Basmati rice")[0] == "usda-168877"
    assert dishes.common_match("Brown rice")[0] == "usda-169703"
    assert dishes.common_match("Salt") is None


def test_a_dishs_numbers_come_from_its_ingredients():
    flour = food("usda-10", "Wheat flour", None, 340, 13, carbs=72, fat=2.5, basis="100g")
    oil = food("usda-11", "Oil", None, 884, 0, carbs=0, fat=100, basis="100g")
    chicken = food("usda-12", "Chicken", None, 120, 22.5, diet="non_vegetarian", basis="100g")
    draft = dishes.compute(
        "Roti and chicken",
        "main",
        2,
        [
            DishIngredient(name="Atta", grams=200, food_id="usda-10"),
            DishIngredient(name="Oil", grams=10, food_id="usda-11"),
            DishIngredient(name="Chicken", grams=200, food_id="usda-12"),
            DishIngredient(name="Garam masala", grams=5),
        ],
        {f["id"]: f for f in (flour, oil, chicken)},
    )
    assert draft.per_serving.kcal == round((680 + 88.4 + 240) / 2)
    assert draft.per_serving.protein_g == pytest.approx((26 + 45) / 2, abs=0.1)
    assert draft.diet == "non_vegetarian" and draft.unmatched == ["Garam masala"]
    assert draft.ingredients[0].kcal == 680


def test_the_chat_prompt_shows_the_week_from_today():
    days = [
        {"day": "2026-10-20", "meals": [{"slot": "lunch", "name": "Old dal", "kind": "meal"}]},
        {"day": "2026-10-22", "meals": [{"slot": "dinner", "name": "Rajma", "kind": "meal"},
                                        {"slot": "lunch", "name": "x", "kind": "eating_out"}]},
    ]  # fmt: skip
    text = chat.prompt(days, date(2026, 10, 21), [], "no paneer", "vegetarian")
    assert "Old dal" not in text and "dinner: Rajma; lunch: eating out" in text
    assert "no paneer" in text and '"type": "replan"' in text


def test_a_named_dish_goes_in_place_of_the_same_kind_of_dish():
    plan = run(generate.build_plan(inputs(meals_per_day=3), None, None, "new_week"))
    day = plan["days"][0]
    foods = {f["id"]: f for f in FOODS}
    lunch = day["meals"][1]
    staple_before = lunch["items"][1]["food_id"]
    other = foods["indb-S2"] if staple_before == "indb-S1" else foods["indb-S1"]
    plans.replace_dish(day, 1, other, foods)
    assert day["meals"][1]["items"][1]["food_id"] != staple_before  # the staple was swapped
    assert day["meals"][1]["items"][0]["food_id"] == lunch["items"][0]["food_id"]
