"""Chatting about the meal plan: the AI turns a message ("no paneer this week",
"aloo paratha for Sunday breakfast", "eating out Saturday night") into changes,
the rules apply them (dishes from the database, portions resized, numbers worked
out), and the result is a preview to use or keep. Dishes that aren't in the
database are offered to add. Spec: context/pages/nutrition-plan.md ("Chat")."""

from datetime import date
from typing import Any

import httpx2
from pydantic import BaseModel

from core.llm import LlmConfig, LlmError, ask_json
from core.models.nutrition import ChatMessage, ChatReply
from core.nutrition import rules
from core.nutrition.generate import build_plan
from core.nutrition.inputs import kept_days, load_inputs, merge_kept
from core.nutrition.plans import (
    active_row,
    foods_by_id,
    get_week,
    mark_eating_out,
    plan_days,
    replace_dish,
    save_draft,
    short_day,
)
from core.supabase import SupabaseClient
from core.workouts.inputs import user_select

HISTORY = 8
# Dish roles that may go in each meal when asked for by name.
SLOT_ROLES = {
    "breakfast": ["breakfast", "snack", "fruit", "protein", "staple"],
    "lunch": ["main", "staple", "salad"],
    "dinner": ["main", "staple", "salad"],
    "snack": ["snack", "fruit", "protein", "breakfast"],
}

SYSTEM = (
    "You help a person adjust this week's meal plan. You turn their message into "
    "changes the app can make, and reply briefly and warmly. Answer with JSON only."
)


class LlmAction(BaseModel):
    # swap: a named dish in one meal; eating_out: a meal eaten out; replan: the rest of
    # the week made again with a request (e.g. more protein, lighter dinners, no paneer).
    type: str
    day: str | None = None
    slot: str | None = None
    dish: str | None = None
    request: str | None = None
    avoid: list[str] = []


class LlmChat(BaseModel):
    reply: str
    actions: list[LlmAction] = []


def plan_text(days: list[dict[str, Any]], today: date) -> str:
    lines = []
    for day in days:
        if day["day"] < today.isoformat():
            continue
        meals = "; ".join(
            f"{m['slot']}: {m['name'] if m['kind'] == 'meal' else 'eating out'}"
            for m in day["meals"]
        )
        lines.append(f"{day['day']} ({short_day(day['day'])}): {meals}")
    return "\n".join(lines)


def prompt(
    days: list[dict[str, Any]], today: date, history: list[dict[str, Any]], text: str, diet: str
) -> str:
    earlier = "\n".join(f"{m['role']}: {m['text']}" for m in history[-HISTORY:]) or "(none)"
    return f"""Today is {today.isoformat()} ({today.strftime("%A")}). Their diet: {diet}.

This week's plan from today:
{plan_text(days, today)}

Earlier in this chat:
{earlier}

Their message: {text}

Changes you can ask for (days from today only, as YYYY-MM-DD; slot is breakfast,
lunch, dinner or snack):
- {{"type": "swap", "day": ..., "slot": ..., "dish": "the dish's usual name"}} for a
  specific dish in a specific meal (one action per dish).
- {{"type": "eating_out", "day": ..., "slot": ...}} for a meal eaten out.
- {{"type": "replan", "request": "what they want, in a sentence", "avoid": ["paneer"]}}
  for anything broader (more protein, lighter dinners, more variety, no paneer, quicker
  breakfasts); "avoid" lists foods to leave out this week.
Examples:
- "no chicken this week, more fish" → one replan: {{"type": "replan", "request": "more
  fish and eggs", "avoid": ["chicken"]}} (never a list of swaps for this).
- "aloo paratha for Sunday breakfast" → one swap with dish "Aloo paratha".
- "Thai green curry on Friday dinner" → one swap with dish "Thai green curry" (always
  ask for a named dish; the app checks whether it's in the database).
If it's a question or nothing needs changing, give no actions and just answer.
The reply is 1-2 sentences; when there are changes, say a preview is ready to check.

Return JSON: {{"reply": "...", "actions": [...]}}"""


def _meal_position(day: dict[str, Any], slot: str | None) -> int | None:
    return next((n for n, m in enumerate(day["meals"]) if m["slot"] == slot), None)


async def history(
    supabase: SupabaseClient, token: str, profile_id: str, week_start: date
) -> list[dict[str, Any]]:
    return await supabase.select(
        "meal_chat_messages",
        {
            "select": "id,role,text,created_at,draft_plan_id,details",
            "profile_id": f"eq.{profile_id}",
            "week_start": f"eq.{week_start.isoformat()}",
            "order": "created_at",
        },
        token,
    )


def to_messages(rows: list[dict[str, Any]]) -> list[ChatMessage]:
    return [
        ChatMessage(
            id=r["id"],
            role=r["role"],
            text=r["text"],
            created_at=r["created_at"],
            draft_plan_id=r.get("draft_plan_id"),
            add_dishes=(r.get("details") or {}).get("add_dishes") or [],
        )
        for r in rows
    ]


async def get_chat(
    supabase: SupabaseClient, token: str, profile_id: str, today: date
) -> list[ChatMessage]:
    return to_messages(await history(supabase, token, profile_id, rules.week_start_of(today)))


async def _store(
    supabase: SupabaseClient,
    token: str,
    profile_id: str,
    week_start: date,
    role: str,
    text: str,
    draft_plan_id: str | None = None,
    add_dishes: list[str] | None = None,
) -> None:
    await supabase.insert(
        "meal_chat_messages",
        {
            "profile_id": profile_id,
            "week_start": week_start.isoformat(),
            "role": role,
            "text": text[:2000],
            "draft_plan_id": draft_plan_id,
            "details": {"add_dishes": add_dishes} if add_dishes else {},
        },
        token,
        returning="id",
    )


async def send(
    supabase: SupabaseClient,
    http: httpx2.AsyncClient,
    llm: LlmConfig | None,
    token: str,
    profile_id: str,
    today: date,
    text: str,
) -> ChatReply:
    week_start = rules.week_start_of(today)
    earlier = await history(supabase, token, profile_id, week_start)
    await _store(supabase, token, profile_id, week_start, "user", text)
    row = await active_row(supabase, token, profile_id, week_start)
    draft_id: str | None = None
    add_dishes: list[str] = []
    if not row:
        reply = "There's no meal plan this week yet. Make one first, then I can change it."
    else:
        try:
            reply, draft_id, add_dishes = await _apply(
                supabase, http, llm, token, profile_id, today, row, earlier, text
            )
        except LlmError:
            reply = "I couldn't reach the AI just now. Please try again in a minute."
    await _store(supabase, token, profile_id, week_start, "assistant", reply, draft_id, add_dishes)
    return ChatReply(
        messages=to_messages(await history(supabase, token, profile_id, week_start)),
        week=await get_week(supabase, token, profile_id, week_start, can_edit=True),
    )


async def _apply(
    supabase: SupabaseClient,
    http: httpx2.AsyncClient,
    llm: LlmConfig | None,
    token: str,
    profile_id: str,
    today: date,
    row: dict[str, Any],
    earlier: list[dict[str, Any]],
    text: str,
) -> tuple[str, str | None, list[str]]:
    """The reply, the preview's id (if anything changed) and dishes to add."""
    if llm is None:
        raise LlmError("No LLM set up")
    week_start = rules.week_start_of(today)
    select = user_select(supabase, token)
    inputs = await load_inputs(select, profile_id, week_start, today)
    days = plan_days(row)
    answer = (
        await ask_json(
            http,
            llm,
            SYSTEM,
            prompt(days, today, earlier, text, inputs.diet_type or "not given"),
            LlmChat,
            500,
        )
    ).value
    notes: list[str] = []
    add_dishes: list[str] = []
    changed = False
    base = row

    replan = [a for a in answer.actions if a.type == "replan"]
    if replan:
        inputs.request = " ".join(a.request or "" for a in replan).strip() or text
        inputs.extra_avoid = [w for a in replan for w in a.avoid if w.strip()]
        inputs.seed = text
        made = await build_plan(inputs, http, llm, "change")
        made = merge_kept(await kept_days(select, profile_id, week_start, today), made)
        days, base, changed = made["days"], made, True

    by_day = {d["day"]: d for d in days}
    avoid = rules.avoid_words(inputs.allergies, [*inputs.dislikes, *inputs.extra_avoid])
    foods = await foods_by_id(
        supabase, token, {i["food_id"] for d in days for m in d["meals"] for i in m["items"]}
    )
    out_refs: set[tuple[str, int]] = set()
    for action in answer.actions:
        day = by_day.get(action.day or "")
        if action.type not in ("swap", "eating_out") or (replan and action.type == "swap"):
            # A replan already chose this week's dishes.
            continue
        if not day or day["day"] < today.isoformat():
            notes.append(f"I can only change meals from today to Sunday ({action.day}).")
            continue
        position = _meal_position(day, action.slot)
        if position is None:
            notes.append(f"There's no {action.slot} on {short_day(day['day'])}.")
            continue
        if action.type == "eating_out":
            out_refs.add((day["day"], position))
            continue
        dish = (action.dish or "").strip()
        roles = SLOT_ROLES.get(action.slot or "lunch", [])
        found = sorted(
            (
                f
                for f in inputs.foods
                if f.get("role") in roles
                and rules.matches_search(f, dish)
                and rules.allowed(f, inputs.diet_type, avoid)
            ),
            # Their own dishes first, then the shortest (closest) name.
            key=lambda f: (
                not rules.matches_search(f, dish, names_only=True),
                f.get("source") != "custom",
                len(f["name"]),
            ),
        )
        if not found:
            add_dishes.append(dish.capitalize())
            continue
        replace_dish(day, position, found[0], foods)
        foods[found[0]["id"]] = found[0]
        changed = True
        if dish.lower() not in rules.display_name(found[0]).lower():
            notes.append(f"Used {rules.display_name(found[0])} for {dish}.")
    if out_refs:
        mark_eating_out(days, out_refs, foods, today)
        changed = True

    if add_dishes:
        names = ", ".join(add_dishes)
        notes.append(f"{names} isn't in the food database yet. Add it, then ask again.")
    if answer.actions and not changed:
        # The AI's reply was written before the changes were tried; none worked.
        reply = " ".join(notes) or "I couldn't make that change."
    else:
        reply = " ".join([answer.reply.strip() or "Done.", *notes])
    if not changed:
        return reply, None, add_dishes
    await save_draft(
        supabase, token, profile_id, week_start, base, days, f"From chat: {text}"[:200]
    )
    draft = await supabase.select(
        "meal_plans",
        {
            "select": "id",
            "profile_id": f"eq.{profile_id}",
            "week_start": f"eq.{week_start.isoformat()}",
            "status": "eq.draft",
        },
        token,
    )
    return reply, (draft[0]["id"] if draft else None), add_dishes
