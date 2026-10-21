from datetime import date

from fastapi import APIRouter, HTTPException, status

from api.deps import CurrentUserDep, HttpDep, SupabaseDep
from core.config import get_settings
from core.llm import LlmError
from core.models.nutrition import (
    ChatMessage,
    ChatReply,
    DishDraft,
    DishInput,
    DraftDish,
    EatingOut,
    FoodOption,
    GenerateMealPlan,
    GroceryList,
    IngredientOption,
    SendChat,
    SwapMeal,
    WeekMealPlan,
)
from core.nutrition import chat, dishes, grocery, rules
from core.nutrition import plans as service
from core.profiles import ProfileNotInHouseholdError, is_own_visible_profile, own_profile_id

router = APIRouter(prefix="/api", tags=["nutrition"])


def _monday(week_start: date) -> date:
    if week_start.weekday() != 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "week_start must be a Monday")
    return week_start


@router.get("/profiles/{profile_id}/meal-plan")
async def week_plan(
    profile_id: str, week_start: date, user: CurrentUserDep, supabase: SupabaseDep
) -> WeekMealPlan:
    """A person's meal plan for a week (active, plus a draft preview on your own)."""
    try:
        is_own = await is_own_visible_profile(supabase, user.access_token, user.id, profile_id)
    except ProfileNotInHouseholdError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile not found") from error
    return await service.get_week(
        supabase, user.access_token, profile_id, _monday(week_start), is_own
    )


@router.post("/me/meal-plan/generate")
async def generate(
    body: GenerateMealPlan, user: CurrentUserDep, supabase: SupabaseDep, http: HttpDep
) -> WeekMealPlan:
    """Make this week's meal plan (from `today` on). With reason `new_week` nothing
    happens if the week already has one. Tried straight away; otherwise the Mac
    worker makes it (`generating` is true until then). `missing` lists what's
    needed first (e.g. a weigh-in)."""
    profile_id = await own_profile_id(supabase, user.access_token, user.id)
    return await service.generate(
        supabase, http, get_settings().llm, user.access_token, profile_id, body.today, body.reason
    )


async def _own_week(supabase, user, plan_id: str) -> WeekMealPlan:
    profile_id = await own_profile_id(supabase, user.access_token, user.id)
    week_start = await service.week_of_plan(supabase, user.access_token, plan_id)
    return await service.get_week(
        supabase,
        user.access_token,
        profile_id,
        week_start or rules.week_start_of(date.today()),
        True,
    )


@router.post("/me/meal-plans/{plan_id}/apply")
async def apply(plan_id: str, user: CurrentUserDep, supabase: SupabaseDep) -> WeekMealPlan:
    """Use the previewed draft as the week's meal plan."""
    try:
        await service.apply_draft(supabase, user.access_token, plan_id)
    except service.PlanNotFoundError as error:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No draft plan of yours with that id"
        ) from error
    return await _own_week(supabase, user, plan_id)


@router.delete("/me/meal-plans/{plan_id}")
async def discard(plan_id: str, user: CurrentUserDep, supabase: SupabaseDep) -> WeekMealPlan:
    """Throw away a draft (keep the current plan)."""
    profile_id = await own_profile_id(supabase, user.access_token, user.id)
    week_start = await service.week_of_plan(supabase, user.access_token, plan_id)
    if week_start is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plan not found")
    await service.discard_draft(supabase, user.access_token, profile_id, plan_id)
    return await service.get_week(supabase, user.access_token, profile_id, week_start, True)


@router.get("/me/planned-meals/{meal_id}/alternatives")
async def alternatives(
    meal_id: str,
    today: date,
    user: CurrentUserDep,
    supabase: SupabaseDep,
    item: int = 0,
    search: str | None = None,
) -> list[FoodOption]:
    """Swaps for one dish in a meal (`item`): the same kind of dish that fits your diet
    and allergies; with `search`, any dish whose name matches (your own included)."""
    profile_id = await own_profile_id(supabase, user.access_token, user.id)
    try:
        return await service.alternatives(
            supabase, user.access_token, profile_id, meal_id, today, item, search
        )
    except service.PlanNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Meal not in your plan") from error


@router.put("/me/planned-meals/{meal_id}/food")
async def swap(
    meal_id: str, body: SwapMeal, today: date, user: CurrentUserDep, supabase: SupabaseDep
) -> WeekMealPlan:
    """Swap a meal's main dish for one of its alternatives; the meal is resized."""
    profile_id = await own_profile_id(supabase, user.access_token, user.id)
    try:
        plan_id = await service.swap(
            supabase,
            user.access_token,
            profile_id,
            meal_id,
            body.food_id,
            today,
            body.item,
            body.search,
        )
    except service.PlanNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Meal not in your plan") from error
    except service.NotAnAlternativeError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Pick one of the suggested swaps"
        ) from error
    return await _own_week(supabase, user, plan_id)


@router.post("/me/meal-plan/eating-out")
async def eating_out(body: EatingOut, user: CurrentUserDep, supabase: SupabaseDep) -> WeekMealPlan:
    """Mark meals as eaten out: returns a preview with the rest of the week rebalanced."""
    profile_id = await own_profile_id(supabase, user.access_token, user.id)
    try:
        return await service.eating_out(
            supabase, user.access_token, profile_id, body.meal_ids, body.today
        )
    except service.ChangeError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error


@router.get("/grocery-list")
async def grocery_list(
    week_start: date,
    from_day: date,
    user: CurrentUserDep,
    supabase: SupabaseDep,
    profile_id: str | None = None,
) -> GroceryList:
    """What the household's meal plans need from `from_day` to Sunday, added up
    (or one person's, with `profile_id`)."""
    return await grocery.grocery_list(
        supabase, user.access_token, _monday(week_start), from_day, profile_id
    )


# --- Chat --------------------------------------------------------------------------------


@router.get("/me/meal-chat")
async def get_chat(today: date, user: CurrentUserDep, supabase: SupabaseDep) -> list[ChatMessage]:
    """This week's chat about your meal plan."""
    profile_id = await own_profile_id(supabase, user.access_token, user.id)
    return await chat.get_chat(supabase, user.access_token, profile_id, today)


@router.post("/me/meal-chat")
async def send_chat(
    body: SendChat, user: CurrentUserDep, supabase: SupabaseDep, http: HttpDep
) -> ChatReply:
    """Ask for a change in your own words; changes come back as a preview to use or keep."""
    profile_id = await own_profile_id(supabase, user.access_token, user.id)
    return await chat.send(
        supabase, http, get_settings().llm, user.access_token, profile_id, body.today, body.text
    )


# --- Your own dishes ------------------------------------------------------------------------


@router.post("/me/dishes/draft")
async def draft_dish(
    body: DraftDish, user: CurrentUserDep, supabase: SupabaseDep, http: HttpDep
) -> DishDraft:
    """The AI's recipe for a dish, matched to the ingredient database, to check first."""
    try:
        return await dishes.draft(
            supabase, http, get_settings().llm, user.access_token, body.name, body.note
        )
    except LlmError as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Couldn't reach the AI just now. Please try again in a minute.",
        ) from error


@router.post("/me/dishes/preview")
async def preview_dish(body: DishInput, user: CurrentUserDep, supabase: SupabaseDep) -> DishDraft:
    """The numbers for an edited recipe."""
    return await dishes.preview(supabase, user.access_token, body)


@router.post("/me/dishes")
async def save_dish(body: DishInput, user: CurrentUserDep, supabase: SupabaseDep) -> FoodOption:
    """Save a dish for your household; the planner, swaps and chat can then use it."""
    profile_id = await own_profile_id(supabase, user.access_token, user.id)
    try:
        return await dishes.save(supabase, user.access_token, profile_id, body)
    except dishes.DishError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error


@router.get("/me/dishes")
async def household_dishes(user: CurrentUserDep, supabase: SupabaseDep) -> list[FoodOption]:
    """Dishes your household has added."""
    return await dishes.household_dishes(supabase, user.access_token)


@router.delete("/me/dishes/{dish_id}")
async def remove_dish(dish_id: str, user: CurrentUserDep, supabase: SupabaseDep) -> None:
    """Remove a dish you added (plans that use it keep it)."""
    profile_id = await own_profile_id(supabase, user.access_token, user.id)
    await dishes.remove(supabase, user.access_token, profile_id, dish_id)


@router.get("/ingredients")
async def ingredients(
    search: str, user: CurrentUserDep, supabase: SupabaseDep
) -> list[IngredientOption]:
    """Ingredients (USDA, per 100 g) matching a name, to match a recipe's ingredient."""
    return await dishes.search_ingredients(supabase, user.access_token, search)
