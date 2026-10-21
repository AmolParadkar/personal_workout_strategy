"""Weekly meal plans: reading a week, making a plan (Vercel first, then the Mac
worker), applying or discarding a draft, swapping a dish, eating out (a preview
that rebalances the rest of the week) and the household grocery list.
Spec: context/pages/nutrition-plan.md; flow: context/architecture.md
("Regenerating a plan")."""

import asyncio
from datetime import date, datetime
from typing import Any

import httpx2

from core.jobs import queue
from core.llm import LlmConfig, LlmError
from core.models.nutrition import (
    DailyTargets,
    FoodOption,
    MealDay,
    MealItem,
    MealPlan,
    Nutrients,
    PlannedMeal,
    WeekMealPlan,
)
from core.nutrition import rules
from core.nutrition.generate import MAX_FAT_SHARE, build_plan, fat_share, size
from core.nutrition.inputs import (
    FOOD_COLUMNS,
    MissingDetailsError,
    kept_days,
    load_inputs,
    merge_kept,
    missing_details,
    status_to_save,
)
from core.nutrition.rules import Portion
from core.supabase import SupabaseClient
from core.workouts.inputs import user_select

PLAN_JOB = "generate_meal_plan"
VERCEL_BUDGET_SECONDS = 25.0
SWAP_COUNT = 6
# A meal out is usually richer than the one planned.
EATING_OUT_EXTRA = 0.3
# Most a day's planned calories are trimmed to make up for a meal out.
MOST_TRIM = 0.10


class PlanNotFoundError(Exception):
    pass


class NotAnAlternativeError(Exception):
    """The chosen food isn't one of the offered swaps."""


class ChangeError(Exception):
    """A change that can't be made, with a message for the person."""


# --- Reading a week -----------------------------------------------------------------------

PLAN_SELECT = (
    "id,week_start,status,rationale,made_by,reason,change_note,created_at,"
    "daily_targets(day,kcal,protein_g,carbs_g,fat_g,fibre_g,micros,reasons,training_minutes),"
    "planned_meals(id,day,slot,position,kind,name,items,nutrients,note)"
)


def totals(meals: list[dict[str, Any]]) -> Nutrients:
    out = rules.empty()
    for meal in meals:
        n = meal.get("nutrients") or {}
        out = rules.add(
            out,
            {**{k: float(n.get(k) or 0) for k in rules.NUTRIENT_KEYS}, "micros": n.get("micros")},
        )
    return Nutrients(**rules.rounded(out))


def to_plan(row: dict[str, Any]) -> MealPlan:
    meals_by_day: dict[str, list[dict[str, Any]]] = {}
    for meal in row.get("planned_meals") or []:
        meals_by_day.setdefault(meal["day"], []).append(meal)
    days = []
    for target in sorted(row.get("daily_targets") or [], key=lambda t: t["day"]):
        meals = sorted(meals_by_day.get(target["day"], []), key=lambda m: m["position"])
        days.append(
            MealDay(
                day=target["day"],
                targets=DailyTargets(**{k: v for k, v in target.items() if k != "day"}),
                meals=[
                    PlannedMeal(
                        id=m["id"],
                        slot=m["slot"],
                        position=m["position"],
                        kind=m["kind"],
                        name=m["name"],
                        items=[MealItem(**i) for i in m.get("items") or []],
                        nutrients=Nutrients(**(m.get("nutrients") or {})),
                        note=m.get("note"),
                    )
                    for m in meals
                ],
                totals=totals(meals),
            )
        )
    return MealPlan(
        id=row["id"],
        week_start=row["week_start"],
        status=row["status"],
        rationale=row.get("rationale"),
        made_by=row.get("made_by"),
        reason=row.get("reason"),
        change_note=row.get("change_note"),
        created_at=row["created_at"],
        days=days,
    )


async def _generating(
    supabase: SupabaseClient, token: str, profile_id: str, week_start: date
) -> bool:
    rows = await supabase.select(
        "jobs",
        {
            "select": "id",
            "type": f"eq.{PLAN_JOB}",
            "status": "in.(pending,processing)",
            "payload->>profile_id": f"eq.{profile_id}",
            "payload->>week_start": f"eq.{week_start.isoformat()}",
        },
        token,
    )
    return bool(rows)


async def get_week(
    supabase: SupabaseClient, token: str, profile_id: str, week_start: date, can_edit: bool
) -> WeekMealPlan:
    rows = await supabase.select(
        "meal_plans",
        {
            "select": PLAN_SELECT,
            "profile_id": f"eq.{profile_id}",
            "week_start": f"eq.{week_start.isoformat()}",
            "status": "in.(active,draft)",
        },
        token,
    )
    by_status = {row["status"]: to_plan(row) for row in rows}
    missing: list[str] = []
    if can_edit and "active" not in by_status:
        missing = await missing_details(user_select(supabase, token), profile_id)
    return WeekMealPlan(
        week_start=week_start,
        active=by_status.get("active"),
        draft=by_status.get("draft") if can_edit else None,
        generating=await _generating(supabase, token, profile_id, week_start),
        can_edit=can_edit,
        missing=missing,
    )


# --- Making a plan ---------------------------------------------------------------------------


async def save(
    supabase: SupabaseClient, token: str, profile_id: str, week_start: date, status: str, plan
) -> None:
    await supabase.rpc(
        "save_meal_plan",
        {
            "p_profile_id": profile_id,
            "p_week_start": week_start.isoformat(),
            "p_status": status,
            "p_plan": plan,
        },
        token,
    )


async def generate(
    supabase: SupabaseClient,
    http: httpx2.AsyncClient,
    llm: LlmConfig | None,
    token: str,
    profile_id: str,
    today: date,
    reason: str,
    budget_seconds: float = VERCEL_BUDGET_SECONDS,
) -> WeekMealPlan:
    """Make this week's meal plan. Active if the week has none, otherwise a draft
    to preview. Tried straight away with Groq; if that's slow or fails, the Mac
    worker makes it (Groq, then Ollama, then rules)."""
    week_start = rules.week_start_of(today)
    week = await get_week(supabase, token, profile_id, week_start, can_edit=True)
    if week.generating or week.missing or (reason == "new_week" and (week.active or week.draft)):
        return week
    status = "draft" if week.active else "active"
    select = user_select(supabase, token)
    seed = _seed(reason)
    try:
        if llm is None or not llm.groq_api_key:
            raise LlmError("No cloud LLM on the API")
        inputs = await load_inputs(select, profile_id, week_start, today, seed)
        plan = await asyncio.wait_for(
            build_plan(inputs, http, llm, reason, rules_only_if_llm_fails=False), budget_seconds
        )
        plan = merge_kept(await kept_days(select, profile_id, week_start, today), plan)
        final = await status_to_save(select, profile_id, week_start, status, reason)
        if final:
            await save(supabase, token, profile_id, week_start, final, plan)
    except MissingDetailsError:
        pass
    except (LlmError, TimeoutError, httpx2.HTTPError):
        await queue.enqueue(
            supabase,
            token,
            profile_id,
            PLAN_JOB,
            {
                "profile_id": profile_id,
                "week_start": week_start.isoformat(),
                "today": today.isoformat(),
                "status": status,
                "reason": reason,
                "seed": seed,
            },
        )
    return await get_week(supabase, token, profile_id, week_start, can_edit=True)


def _seed(reason: str) -> str:
    # "Make a new plan" should give different dishes each time it's asked.
    return datetime.now().isoformat() if reason == "requested" else ""


async def apply_draft(supabase: SupabaseClient, token: str, plan_id: str) -> None:
    try:
        await supabase.rpc("apply_meal_plan", {"p_plan_id": plan_id}, token)
    except httpx2.HTTPStatusError as error:
        raise PlanNotFoundError from error


async def discard_draft(
    supabase: SupabaseClient, token: str, profile_id: str, plan_id: str
) -> None:
    await supabase.delete(
        "meal_plans",
        {"id": f"eq.{plan_id}", "profile_id": f"eq.{profile_id}", "status": "eq.draft"},
        token,
    )


async def week_of_plan(supabase: SupabaseClient, token: str, plan_id: str) -> date | None:
    rows = await supabase.select(
        "meal_plans", {"select": "week_start", "id": f"eq.{plan_id}"}, token
    )
    return date.fromisoformat(rows[0]["week_start"]) if rows else None


# --- Rebuilding a meal from the foods table --------------------------------------------------


async def foods_by_id(
    supabase: SupabaseClient, token: str, ids: set[str]
) -> dict[str, dict[str, Any]]:
    if not ids:
        return {}
    rows = await supabase.select(
        "foods", {"select": FOOD_COLUMNS, "id": f"in.({','.join(sorted(ids))})"}, token
    )
    return {r["id"]: r for r in rows}


def portions_of(meal: dict[str, Any], foods: dict[str, dict[str, Any]]) -> list[Portion]:
    """A saved meal's items as portions; the staple (or the only dish) is the one
    resized, as when the plan was made."""
    items = [i for i in meal.get("items") or [] if i["food_id"] in foods]
    flexible = 1 if meal["slot"] in ("lunch", "dinner") and len(items) > 1 else 0
    return [
        Portion(foods[i["food_id"]], float(i["servings"]), flexible=n == flexible)
        for n, i in enumerate(items)
    ]


def slot_target(day_kcal: float, slots: list[str], position: int) -> float:
    return rules.slot_kcal(day_kcal, slots)[position]


async def _own_meal(
    supabase: SupabaseClient, token: str, profile_id: str, meal_id: str
) -> dict[str, Any]:
    rows = await supabase.select(
        "planned_meals",
        {
            "select": "id,day,slot,position,kind,name,items,nutrients,note,meal_plan_id,"
            "meal_plans(status,daily_targets(day,kcal),planned_meals(day,slot,position))",
            "id": f"eq.{meal_id}",
            "profile_id": f"eq.{profile_id}",
        },
        token,
    )
    if not rows:
        raise PlanNotFoundError
    return rows[0]


# --- Swapping a dish -------------------------------------------------------------------------


async def alternatives(
    supabase: SupabaseClient, token: str, profile_id: str, meal_id: str, today: date
) -> list[FoodOption]:
    """Dishes in the same role (main, breakfast, staple, …) the person can have,
    closest in protein for their calories first."""
    meal = await _own_meal(supabase, token, profile_id, meal_id)
    items = meal.get("items") or []
    if meal["kind"] != "meal" or not items:
        return []
    lead_id = items[0]["food_id"]
    inputs = await load_inputs(
        user_select(supabase, token), profile_id, rules.week_start_of(today), today
    )
    lead = next((f for f in inputs.foods if f["id"] == lead_id), None)
    if lead is None:
        return []
    avoid = rules.avoid_words(inputs.allergies, inputs.dislikes)
    in_meal = {i["food_id"] for i in items}
    density = _density(lead)
    pool = [
        f
        for f in inputs.foods
        if f.get("role") == lead.get("role")
        and f["id"] not in in_meal
        and (f.get("alias") or fat_share(f) <= MAX_FAT_SHARE)
        and rules.allowed(f, inputs.diet_type, avoid)
    ]
    pool.sort(key=lambda f: (abs(_density(f) - density), rules.display_name(f)))
    return [_option(f) for f in pool[:SWAP_COUNT]]


def _density(food: dict[str, Any]) -> float:
    n = rules.nutrients(food, 1)
    return n["protein_g"] / n["kcal"] if n["kcal"] else 0


def _option(food: dict[str, Any]) -> FoodOption:
    n = rules.nutrients(food, 1)
    return FoodOption(
        id=food["id"],
        name=rules.display_name(food),
        serving_label=food.get("serving_label"),
        kcal=round(n["kcal"]),
        protein_g=round(n["protein_g"], 1),
        diet=food["diet"],
    )


async def swap(
    supabase: SupabaseClient, token: str, profile_id: str, meal_id: str, food_id: str, today: date
) -> str:
    """Put the chosen dish in place of the meal's main one, resize the meal to its
    share of the day's calories, and return the plan's id."""
    offered = await alternatives(supabase, token, profile_id, meal_id, today)
    if food_id not in {o.id for o in offered}:
        raise NotAnAlternativeError
    meal = await _own_meal(supabase, token, profile_id, meal_id)
    items = meal["items"]
    foods = await foods_by_id(supabase, token, {i["food_id"] for i in items} | {food_id})
    replaced = [{**items[0], "food_id": food_id, "servings": 1}] + items[1:]
    portions = portions_of({**meal, "items": replaced}, foods)
    plan = meal["meal_plans"]
    day_kcal = next(t["kcal"] for t in plan["daily_targets"] if t["day"] == meal["day"])
    slots = [
        m["slot"]
        for m in sorted(plan["planned_meals"], key=lambda m: m["position"])
        if m["day"] == meal["day"]
    ]
    size(meal["slot"], portions, slot_target(day_kcal, slots, meal["position"]))
    rebuilt = rules.meal_json(meal["slot"], meal["position"], portions)
    await supabase.update(
        "planned_meals",
        {"id": f"eq.{meal_id}", "profile_id": f"eq.{profile_id}"},
        {
            "name": rebuilt["name"],
            "items": rebuilt["items"],
            "nutrients": rebuilt["nutrients"],
            "note": None,
        },
        token,
        returning="id",
    )
    return meal["meal_plan_id"]


# --- Eating out --------------------------------------------------------------------------------


def _short(day: str) -> str:
    return date.fromisoformat(day).strftime("%a %d %b")


async def eating_out(
    supabase: SupabaseClient, token: str, profile_id: str, meal_ids: list[str], today: date
) -> WeekMealPlan:
    """A preview of the week with those meals eaten out: each counted as a little
    richer than planned, and one meal on each following day trimmed (up to 10%
    of the day) until that's made up, so the week stays on target."""
    week_start = rules.week_start_of(today)
    rows = await supabase.select(
        "meal_plans",
        {
            "select": PLAN_SELECT,
            "profile_id": f"eq.{profile_id}",
            "week_start": f"eq.{week_start.isoformat()}",
            "status": "eq.active",
        },
        token,
    )
    if not rows:
        raise ChangeError("There's no meal plan this week to change.")
    plan = rows[0]
    meals = plan.get("planned_meals") or []
    chosen = [m for m in meals if m["id"] in set(meal_ids)]
    if len(chosen) != len(set(meal_ids)):
        raise ChangeError("Those meals aren't in this week's plan.")
    if any(m["day"] < today.isoformat() for m in chosen):
        raise ChangeError("Choose meals from today on.")
    if any(m["kind"] == "eating_out" for m in chosen):
        raise ChangeError("That meal is already marked as eating out.")

    targets = {t["day"]: t for t in plan.get("daily_targets") or []}
    slots_by_day: dict[str, list[str]] = {}
    for m in sorted(meals, key=lambda m: m["position"]):
        slots_by_day.setdefault(m["day"], []).append(m["slot"])

    extra = 0.0
    replaced: dict[str, dict[str, Any]] = {}
    for m in chosen:
        t = targets[m["day"]]
        share = slot_target(t["kcal"], slots_by_day[m["day"]], m["position"])
        estimate = share * (1 + EATING_OUT_EXTRA)
        extra += estimate - float((m.get("nutrients") or {}).get("kcal") or share)
        ratio = estimate / t["kcal"]
        replaced[m["id"]] = {
            **m,
            "kind": "eating_out",
            "name": "Eating out",
            "items": [],
            "nutrients": {
                "kcal": round(estimate),
                "protein_g": round(t["protein_g"] * ratio * 0.8, 1),
                "carbs_g": round(t["carbs_g"] * ratio, 1),
                "fat_g": round(t["fat_g"] * ratio * 1.4, 1),
                "micros": {},
            },
            "note": "An estimate: a meal out is usually richer. Log what you eat on the day.",
        }

    # Trim the days after the first meal out (or that day's other meals if it's Sunday).
    first = min(m["day"] for m in chosen)
    later = [d for d in sorted(targets) if d > first and d >= today.isoformat()]
    trim_days = later or [first]
    foods = await foods_by_id(
        supabase,
        token,
        {i["food_id"] for m in meals for i in m.get("items") or [] if m["day"] in trim_days},
    )
    # Take what's needed from the next day first (up to 10% of it), then the
    # day after, until the extra is made up, so the smaller portions really show.
    remaining = max(extra, 0.0)
    new_meals: dict[str, dict[str, Any]] = dict(replaced)
    for day in trim_days:
        t = targets[day]
        trim = min(remaining, MOST_TRIM * t["kcal"])
        if trim <= 0:
            break
        day_meals = [
            m for m in meals if m["day"] == day and m["kind"] == "meal" and m["id"] not in replaced
        ]
        # The whole trim on one meal (dinner first), so the smaller portion shows.
        day_meals.sort(key=lambda m: ["dinner", "lunch", "breakfast", "snack"].index(m["slot"]))
        for m in day_meals:
            portions = portions_of(m, foods)
            if not portions:
                continue
            current = float((m.get("nutrients") or {}).get("kcal") or 0)
            size(m["slot"], portions, current - trim)
            rebuilt = rules.meal_json(m["slot"], m["position"], portions, m.get("note"))
            rebuilt.pop("_lead", None)
            if rebuilt["nutrients"]["kcal"] < current:
                new_meals[m["id"]] = {**m, **rebuilt}
                remaining -= current - rebuilt["nutrients"]["kcal"]
                break

    days = []
    for day in sorted(targets):
        t = targets[day]
        day_meals = sorted(
            (new_meals.get(m["id"], m) for m in meals if m["day"] == day),
            key=lambda m: m["position"],
        )
        days.append(
            {
                "day": day,
                "targets": {k: v for k, v in t.items() if k != "day"},
                "meals": [
                    {
                        k: m.get(k)
                        for k in ("slot", "position", "kind", "name", "items", "nutrients", "note")
                    }
                    for m in day_meals
                ],
            }
        )
    note = "Eating out: " + "; ".join(
        f"{_short(m['day'])}, {m['slot']}" for m in sorted(chosen, key=lambda m: m["day"])
    )
    trimmed = (
        f" The other meals {'that day' if not later else 'later in the week'} are a little "
        "smaller to keep the week on target."
        if remaining < extra
        else ""
    )
    draft = {
        "rationale": ((plan.get("rationale") or "") + trimmed).strip()[:2000],
        "made_by": plan.get("made_by"),
        "reason": "change",
        "change_note": note[:200],
        "days": days,
    }
    await save(supabase, token, profile_id, week_start, "draft", draft)
    return await get_week(supabase, token, profile_id, week_start, can_edit=True)
