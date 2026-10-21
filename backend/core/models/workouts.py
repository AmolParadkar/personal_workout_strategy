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
    block_start: date | None = None
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
    # Changes in effect this week (and a pending one being previewed).
    changes: list["PlanChange"] = []
    # A short message, e.g. "Saved: your vacation next week will shape that week's plan."
    message: str | None = None


class GeneratePlan(BaseModel):
    # The person's local date; the plan covers its week (Monday to Sunday) from today on.
    today: date
    # new_week: made automatically for a week without a plan (skipped if one exists);
    # requested: "Make a new plan" (a preview, if there's already a plan).
    reason: Literal["new_week", "requested"] = "requested"


class SwapExercise(BaseModel):
    exercise_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")


# --- Doing the workout (Plan for Today) ---------------------------------------------

Effort = Literal["easy", "right", "too_hard"]


class SetLog(BaseModel):
    id: str
    session_item_id: str
    set_number: int
    reps: int | None
    load_kg: float | None
    duration_seconds: int | None


class LogSet(BaseModel):
    session_item_id: str
    set_number: int = Field(ge=1, le=20)
    reps: int | None = Field(default=None, ge=0, le=200)
    load_kg: float | None = Field(default=None, ge=0, le=500)
    duration_seconds: int | None = Field(default=None, ge=0, le=7200)


class Completion(BaseModel):
    done_on: date
    effort: Effort | None


class CatchUp(BaseModel):
    """An earlier session this week that isn't done yet (it can still be done)."""

    session_id: str
    day: date
    title: str


class TodayWorkout(BaseModel):
    day: date
    has_plan: bool
    session: PlanSession | None
    logs: list[SetLog]
    completion: Completion | None
    catch_up: list[CatchUp]
    # Planned workouts done in a row (rest days don't count; a planned workout
    # not done by the end of its week breaks it).
    streak: int
    can_edit: bool


class CompleteSession(BaseModel):
    # The person's local date it was done (may be later than the planned day).
    done_on: date
    effort: Effort | None = None


# --- Changing the plan ---------------------------------------------------------------

ChangeKind = Literal[
    "day_off", "add_session", "shorter", "vacation", "cheat_meal", "medical", "other"
]


class PlanChangeRequest(BaseModel):
    kind: ChangeKind
    start_date: date
    end_date: date | None = None
    minutes: int | None = Field(default=None, ge=10, le=300)
    vacation_mode: Literal["rest", "travel"] | None = None
    cheat_mode: Literal["spread", "as_planned"] | None = None
    note: str | None = Field(default=None, max_length=500)
    # The person's local date.
    today: date


class PlanChange(BaseModel):
    id: str
    kind: ChangeKind
    start_date: date
    end_date: date | None
    status: Literal["pending", "applied", "discarded"]
    summary: str
    # A medical pause without an end: "I'm back" ends it.
    can_end: bool


class EndChange(BaseModel):
    today: date


WeekPlan.model_rebuild()
