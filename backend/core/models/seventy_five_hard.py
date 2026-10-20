from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, Field

# The six daily rules, in the order they're shown. Must match the database check.
Item = Literal["diet", "workout_1", "workout_2_outdoor", "water", "reading", "photo"]
ITEMS: list[str] = ["diet", "workout_1", "workout_2_outdoor", "water", "reading", "photo"]

TOTAL_DAYS = 75


class ChecklistItem(BaseModel):
    item: Item
    checked: bool


class DayChecklist(BaseModel):
    date: date
    day: int
    items: list[ChecklistItem]
    # Today is always editable; yesterday only until noon.
    editable: bool


class SeventyFiveHardState(BaseModel):
    """Everything the 75 Hard page shows for one person."""

    can_edit: bool
    status: Literal["not_started", "active", "completed"]
    total_days: int = TOTAL_DAYS
    # Today's day number while active, e.g. 12 for "Day 12 of 75".
    day: int | None = None
    today: DayChecklist | None = None
    # Present until noon, when yesterday can still be ticked.
    yesterday: DayChecklist | None = None
    # Most recent date that wasn't completed, which restarted the count at Day 1.
    last_missed_on: date | None = None
    completed_on: date | None = None


class StartChallenge(BaseModel):
    current_day: Annotated[int, Field(ge=1, le=TOTAL_DAYS)]
    # Browser timezone, e.g. "Asia/Kolkata".
    timezone: Annotated[str, Field(min_length=1, max_length=64)]


class SetCheck(BaseModel):
    date: date
    item: Item
    checked: bool
