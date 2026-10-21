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


class SwapMeal(BaseModel):
    food_id: str = Field(min_length=1, max_length=40)


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
