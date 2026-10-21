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
from core.nutrition.generate import (
    MAX_FAT_SHARE,
    build_plan,
    fat_share,
    main_kind,
    portions_for,
    size,
)
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
SWAP_COUNT = 12
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
    """A saved meal's items as portions, resized the same way as when the plan was
    made (the staple carries the size)."""
    items = [i for i in meal.get("items") or [] if i["food_id"] in foods]
    portions = portions_for(meal["slot"], [foods[i["food_id"]] for i in items])
    for portion, i in zip(portions, items, strict=True):
        portion.servings = float(i["servings"])
    return portions


def slot_target(day_kcal: float, slots: list[str], position: int) -> float:
    return rules.slot_kcal(day_kcal, slots)[position]


# A week held in memory: [{"day", "targets", "meals": [{"slot", "position", "kind",
# "name", "items", "nutrients", "note"}]}], as saved by save_meal_plan.
MEAL_FIELDS = ("slot", "position", "kind", "name", "items", "nutrients", "note")


def plan_days(row: dict[str, Any]) -> list[dict[str, Any]]:
    """A saved plan (PLAN_SELECT) as the days save_meal_plan takes."""
    meals = row.get("planned_meals") or []
    return [
        {
            "day": t["day"],
            "targets": {k: v for k, v in t.items() if k != "day"},
            "meals": [
                {k: m.get(k) for k in MEAL_FIELDS}
                for m in sorted(
                    (m for m in meals if m["day"] == t["day"]), key=lambda m: m["position"]
                )
            ],
        }
        for t in sorted(row.get("daily_targets") or [], key=lambda t: t["day"])
    ]


def _share(day: dict[str, Any], position: int) -> float:
    slots = [m["slot"] for m in day["meals"]]
    return slot_target(day["targets"]["kcal"], slots, position)


def _same_kind(a: dict[str, Any], b: dict[str, Any]) -> bool:
    if a.get("role") != b.get("role"):
        return False
    return a.get("role") != "main" or main_kind(a) == main_kind(b)


def replace_dish(
    day: dict[str, Any],
    position: int,
    food: dict[str, Any],
    foods: dict[str, dict[str, Any]],
    item: int | None = None,
) -> None:
    """Put `food` in a meal: in place of item `item`, or of the dish of the same
    kind (a dal for a dal, a sabzi for a sabzi, rice for chapati), or of the main
    dish; then resize the meal to its share of the day."""
    meal = day["meals"][position]
    items = list(meal.get("items") or [])
    if item is None:
        item = next(
            (
                n
                for n, i in enumerate(items)
                if i["food_id"] in foods and _same_kind(foods[i["food_id"]], food)
            ),
            0,
        )
    entry = {"food_id": food["id"], "servings": 1}
    if items:
        items[min(item, len(items) - 1)] = entry
    else:
        items = [entry]
    foods = {**foods, food["id"]: food}
    portions = portions_of({**meal, "items": items}, foods)
    size(meal["slot"], portions, _share(day, position))
    rebuilt = rules.meal_json(meal["slot"], position, portions)
    rebuilt.pop("_lead", None)
    day["meals"][position] = {**meal, **rebuilt, "kind": "meal", "note": None}


def mark_eating_out(
    days: list[dict[str, Any]],
    refs: set[tuple[str, int]],
    foods: dict[str, dict[str, Any]],
    today: date,
) -> bool:
    """Mark meals (day, position) as eaten out: each counted as a little richer
    than planned, and one meal on each following day trimmed (up to 10% of the
    day) until that's made up. Returns whether anything was trimmed."""
    by_day = {d["day"]: d for d in days}
    extra = 0.0
    for day_iso, position in refs:
        day = by_day[day_iso]
        meal = day["meals"][position]
        t = day["targets"]
        share = _share(day, position)
        estimate = share * (1 + EATING_OUT_EXTRA)
        extra += estimate - float((meal.get("nutrients") or {}).get("kcal") or share)
        ratio = estimate / t["kcal"]
        day["meals"][position] = {
            **meal,
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

    # Take what's needed from the next day first (up to 10% of it), then the day
    # after, until it's made up (that day's other meals if it's the last day).
    first = min(day for day, _ in refs)
    later = [d for d in sorted(by_day) if d > first and d >= today.isoformat()] or [first]
    remaining = max(extra, 0.0)
    for day_iso in later:
        day = by_day[day_iso]
        trim = min(remaining, MOST_TRIM * day["targets"]["kcal"])
        if trim <= 0:
            break
        order = sorted(
            (n for n, m in enumerate(day["meals"]) if m["kind"] == "meal"),
            key=lambda n: ["dinner", "lunch", "breakfast", "snack"].index(day["meals"][n]["slot"]),
        )
        # The whole trim on one meal (dinner first), so the smaller portion shows.
        for n in order:
            meal = day["meals"][n]
            portions = portions_of(meal, foods)
            if not portions:
                continue
            current = float((meal.get("nutrients") or {}).get("kcal") or 0)
            size(meal["slot"], portions, current - trim)
            rebuilt = rules.meal_json(meal["slot"], n, portions, meal.get("note"))
            rebuilt.pop("_lead", None)
            if rebuilt["nutrients"]["kcal"] < current:
                day["meals"][n] = {**meal, **rebuilt}
                remaining -= current - rebuilt["nutrients"]["kcal"]
                break
    return remaining < extra


async def active_row(
    supabase: SupabaseClient, token: str, profile_id: str, week_start: date
) -> dict[str, Any] | None:
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
    return rows[0] if rows else None


async def save_draft(
    supabase: SupabaseClient,
    token: str,
    profile_id: str,
    week_start: date,
    base: dict[str, Any],
    days: list[dict[str, Any]],
    note: str,
    rationale_extra: str = "",
) -> None:
    await save(
        supabase,
        token,
        profile_id,
        week_start,
        "draft",
        {
            "rationale": ((base.get("rationale") or "") + rationale_extra).strip()[:2000],
            "made_by": base.get("made_by"),
            "reason": "change",
            "change_note": note[:200],
            "days": days,
        },
    )


# --- Swapping a dish -------------------------------------------------------------------------


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


async def alternatives(
    supabase: SupabaseClient,
    token: str,
    profile_id: str,
    meal_id: str,
    today: date,
    item: int = 0,
    search: str | None = None,
) -> list[FoodOption]:
    """Swaps for one dish in a meal: the same kind of dish (a dal for a dal, a
    sabzi for a sabzi, …) the person can have, closest in protein for their
    calories first; with `search`, any dish of that kind whose name matches,
    the household's own dishes included."""
    meal = await _own_meal(supabase, token, profile_id, meal_id)
    items = meal.get("items") or []
    if meal["kind"] != "meal" or not items:
        return []
    current_id = items[min(item, len(items) - 1)]["food_id"]
    inputs = await load_inputs(
        user_select(supabase, token), profile_id, rules.week_start_of(today), today
    )
    current = next((f for f in inputs.foods if f["id"] == current_id), None)
    if current is None:
        return []
    avoid = rules.avoid_words(inputs.allergies, inputs.dislikes)
    in_meal = {i["food_id"] for i in items}
    words = [w.lower() for w in (search or "").split() if w]
    pool = [
        f
        for f in inputs.foods
        if f["id"] not in in_meal
        and rules.allowed(f, inputs.diet_type, avoid)
        and (
            rules.matches_search(f, search or "")
            if words
            else _same_kind(f, current)
            and (f.get("alias") or f.get("source") == "custom" or fat_share(f) <= MAX_FAT_SHARE)
        )
    ]
    if words:
        # Dishes named that way before dishes that only contain it.
        pool.sort(
            key=lambda f: (
                not rules.matches_search(f, search or "", names_only=True),
                not _same_kind(f, current),
                len(f["name"]),
            )
        )
    else:
        density = _density(current)
        pool.sort(
            key=lambda f: (
                f.get("source") != "custom",
                abs(_density(f) - density),
                rules.display_name(f),
            )
        )
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
        custom=food.get("source") == "custom",
    )


async def swap(
    supabase: SupabaseClient,
    token: str,
    profile_id: str,
    meal_id: str,
    food_id: str,
    today: date,
    item: int = 0,
    search: str | None = None,
) -> str:
    """Put the chosen dish in place of item `item`, resize the meal to its share
    of the day's calories, and return the plan's id."""
    offered = await alternatives(supabase, token, profile_id, meal_id, today, item, search)
    if food_id not in {o.id for o in offered}:
        raise NotAnAlternativeError
    meal = await _own_meal(supabase, token, profile_id, meal_id)
    foods = await foods_by_id(supabase, token, {i["food_id"] for i in meal["items"]} | {food_id})
    plan = meal["meal_plans"]
    day_meals = sorted(
        (m for m in plan["planned_meals"] if m["day"] == meal["day"]), key=lambda m: m["position"]
    )
    day = {
        "day": meal["day"],
        "targets": next(t for t in plan["daily_targets"] if t["day"] == meal["day"]),
        "meals": [meal if m["position"] == meal["position"] else m for m in day_meals],
    }
    replace_dish(day, meal["position"], foods[food_id], foods, item)
    rebuilt = day["meals"][meal["position"]]
    await supabase.update(
        "planned_meals",
        {"id": f"eq.{meal_id}", "profile_id": f"eq.{profile_id}"},
        {k: rebuilt[k] for k in ("name", "items", "nutrients", "note")},
        token,
        returning="id",
    )
    return meal["meal_plan_id"]


# --- Eating out --------------------------------------------------------------------------------


def short_day(day: str) -> str:
    return date.fromisoformat(day).strftime("%a %d %b")


async def eating_out(
    supabase: SupabaseClient, token: str, profile_id: str, meal_ids: list[str], today: date
) -> WeekMealPlan:
    """A preview of the week with those meals eaten out (see mark_eating_out)."""
    week_start = rules.week_start_of(today)
    row = await active_row(supabase, token, profile_id, week_start)
    if not row:
        raise ChangeError("There's no meal plan this week to change.")
    meals = row.get("planned_meals") or []
    chosen = [m for m in meals if m["id"] in set(meal_ids)]
    if len(chosen) != len(set(meal_ids)):
        raise ChangeError("Those meals aren't in this week's plan.")
    if any(m["day"] < today.isoformat() for m in chosen):
        raise ChangeError("Choose meals from today on.")
    if any(m["kind"] == "eating_out" for m in chosen):
        raise ChangeError("That meal is already marked as eating out.")
    days = plan_days(row)
    foods = await foods_by_id(
        supabase, token, {i["food_id"] for m in meals for i in m.get("items") or []}
    )
    trimmed = mark_eating_out(days, {(m["day"], m["position"]) for m in chosen}, foods, today)
    note = "Eating out: " + "; ".join(
        f"{short_day(m['day'])}, {m['slot']}" for m in sorted(chosen, key=lambda m: m["day"])
    )
    extra = (
        " Other meals later in the week are a little smaller to keep the week on target."
        if trimmed
        else ""
    )
    await save_draft(supabase, token, profile_id, week_start, row, days, note, extra)
    return await get_week(supabase, token, profile_id, week_start, can_edit=True)
