"""Workout plans as the website sees them (context/pages/workout-plan.md)."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

Phase = Literal["cardio", "mobility", "activation", "main", "cooldown"]
PHASE_ORDER: list[str] = ["cardio", "mobility", "activation", "main", "cooldown"]


class PlanItem(BaseModel):
    id: str
    phase: Phase
    position: int
    exercise_id: str
    exercise_name: str
    image: str | None
    primary_muscles: list[str]
    sets: int | None
    reps_min: int | None
    reps_max: int | None
    duration_seconds: int | None
    rest_seconds: int | None
    target_load_kg: float | None
    notes: str | None


class PlanSession(BaseModel):
    id: str
    day: date
    title: str
    focus: str
    minutes: int
    explanation: str | None
    items: list[PlanItem]


class MuscleSets(BaseModel):
    muscle: str
    # Working sets this week (main and activation); secondary muscles count half.
    sets: float


class Plan(BaseModel):
    id: str
    week_start: date
    status: Literal["draft", "active", "superseded"]
    rationale: str | None
    made_by: str | None
    reason: str | None
    created_at: datetime
    sessions: list[PlanSession]
    coverage: list[MuscleSets]


class WeekPlan(BaseModel):
    week_start: date
    active: Plan | None
    # A new plan waiting to be applied or discarded (preview).
    draft: Plan | None
    # A plan is being made (queued for the Mac worker).
    generating: bool
    can_edit: bool


class GeneratePlan(BaseModel):
    # The person's local date; the plan covers its week (Monday to Sunday) from today on.
    today: date
    # new_week: made automatically for a week without a plan (skipped if one exists);
    # requested: "Make a new plan" (a preview, if there's already a plan).
    reason: Literal["new_week", "requested"] = "requested"


class SwapExercise(BaseModel):
    exercise_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")
