"""Meal plans, daily targets and the grocery list as the website sees them
(context/pages/nutrition-plan.md)."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

Slot = Literal["breakfast", "lunch", "dinner", "snack"]


class Nutrients(BaseModel):
    kcal: float = 0
    protein_g: float = 0
    carbs_g: float = 0
    fat_g: float = 0
    fibre_g: float | None = None
    # e.g. {"iron_mg": 12.5, "calcium_mg": 640}
    micros: dict[str, float] = {}


class MealItem(BaseModel):
    food_id: str
    name: str
    servings: float
    # e.g. "2 chapatis", "1 bowl", "100 g"
    unit: str
    grams: float | None = None
    # Dishes: the main raw ingredients for this amount, e.g. "Made with about 110 g
    # green gram, 130 g potato, 20 g oil".
    made_with: str | None = None


class PlannedMeal(BaseModel):
    id: str
    slot: Slot
    position: int
    kind: Literal["meal", "eating_out"]
    name: str
    items: list[MealItem]
    nutrients: Nutrients
    note: str | None


class DailyTargets(BaseModel):
    kcal: int
    protein_g: int
    carbs_g: int
    fat_g: int
    fibre_g: int | None
    # e.g. {"iron_mg": 18, "sodium_mg_max": 2300}
    micros: dict[str, float]
    # One line per target: kcal, protein_g, carbs_g, fat_g, fibre_g, micros.
    reasons: dict[str, str]
    training_minutes: int


class MealDay(BaseModel):
    day: date
    targets: DailyTargets
    meals: list[PlannedMeal]
    # What the planned meals add up to.
    totals: Nutrients


class MealPlan(BaseModel):
    id: str
    week_start: date
    status: Literal["draft", "active", "superseded"]
    rationale: str | None
    made_by: str | None
    reason: str | None
    # For a change preview, e.g. "Eating out: Sat 24 Oct, dinner".
    change_note: str | None
    created_at: datetime
    days: list[MealDay]


class WeekMealPlan(BaseModel):
    week_start: date
    active: MealPlan | None
    # A new plan waiting to be applied or discarded (preview).
    draft: MealPlan | None
    # A plan is being made (queued for the Mac worker).
    generating: bool
    can_edit: bool
    # Needed before a plan can be made, e.g. ["weight"] (your own plan only).
    missing: list[str] = []


class GenerateMealPlan(BaseModel):
    # The person's local date; the plan covers its week from today on.
    today: date
    # new_week: made automatically for a week without a plan (skipped if one exists);
    # requested: "Make a new plan" (a preview, if there's already a plan).
    reason: Literal["new_week", "requested"] = "requested"


class FoodOption(BaseModel):
    id: str
    name: str
    serving_label: str | None
    # For one serving.
    kcal: float
    protein_g: float
    diet: Literal["vegetarian", "eggetarian", "non_vegetarian"]
    # One of the household's own dishes.
    custom: bool = False


class SwapMeal(BaseModel):
    food_id: str = Field(min_length=1, max_length=60)
    # Which dish in the meal (0: the first).
    item: int = Field(default=0, ge=0, le=6)
    # The search the dish was found with, if any.
    search: str | None = Field(default=None, max_length=60)


class EatingOut(BaseModel):
    today: date
    # The planned meals you'll eat out instead.
    meal_ids: list[str] = Field(min_length=1, max_length=14)


class GroceryItem(BaseModel):
    name: str
    # Empty for things bought by count or measured loosely (e.g. sprigs).
    amount: float | None
    unit: str
    # Whose meals need it (display names).
    for_people: list[str]


class GroceryGroup(BaseModel):
    group: str
    items: list[GroceryItem]


class GroceryPerson(BaseModel):
    profile_id: str
    name: str
    has_plan: bool


class GroceryList(BaseModel):
    week_start: date
    # The list covers meals from this day to Sunday.
    from_day: date
    people: list[GroceryPerson]
    groups: list[GroceryGroup]


# --- The household's own dishes ------------------------------------------------------

DishRole = Literal["breakfast", "main", "staple", "salad", "snack"]


class DishIngredient(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    # For the whole recipe.
    grams: float = Field(gt=0, le=5000)
    # The ingredient database entry its nutrients come from (USDA); empty: not matched.
    food_id: str | None = Field(default=None, max_length=40)
    food_name: str | None = None
    # The closest entry there is, not an exact one (e.g. paneer → ricotta).
    approximate: bool = False
    kcal: float = 0
    protein_g: float = 0


class DishDraft(BaseModel):
    name: str
    role: DishRole
    serves: int
    diet: Literal["vegetarian", "eggetarian", "non_vegetarian"]
    ingredients: list[DishIngredient]
    # For one serving, worked out from the matched ingredients.
    per_serving: Nutrients
    # Ingredients with no match (left out of the numbers).
    unmatched: list[str]


class DraftDish(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    # Anything that helps, e.g. "my mother's recipe, no onion or garlic".
    note: str | None = Field(default=None, max_length=300)


class DishInput(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    role: DishRole
    serves: int = Field(ge=1, le=20)
    ingredients: list[DishIngredient] = Field(min_length=1, max_length=30)


class IngredientOption(BaseModel):
    id: str
    name: str
    # Per 100 g.
    kcal: float
    protein_g: float


# --- The week's chat about the meal plan ----------------------------------------------


class ChatMessage(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    text: str
    created_at: datetime
    # A preview this reply made.
    draft_plan_id: str | None = None
    # Dishes the reply suggests adding to the database.
    add_dishes: list[str] = []


class SendChat(BaseModel):
    today: date
    text: str = Field(min_length=1, max_length=1000)


class ChatReply(BaseModel):
    messages: list[ChatMessage]
    week: WeekMealPlan
