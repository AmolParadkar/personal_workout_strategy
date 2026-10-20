"""Settings / Profile page models. Allowed values mirror the database checks
(supabase/migrations/), so bad input is rejected with a clear message before
it reaches the database."""

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

Sex = Literal["female", "male", "other"]
Goal = Literal[
    "lose_fat", "build_muscle", "get_stronger", "endurance", "general_health", "mobility"
]
GoalMetric = Literal[
    "weight", "body_fat", "vo2_max", "resting_hr", "hrv", "strength", "steps", "sleep"
]
Day = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
Location = Literal["home", "gym", "travel"]
Equipment = Literal[
    "bodyweight",
    "dumbbells",
    "barbell",
    "kettlebell",
    "resistance_bands",
    "pull_up_bar",
    "bench",
    "cable_machine",
    "treadmill",
    "exercise_bike",
    "rowing_machine",
    "full_gym",
]
DietType = Literal["vegetarian", "eggetarian", "non_vegetarian"]
# Health apps and devices a person uses ("Apps and devices you use" in Settings).
DataSource = Literal[
    "iphone_health",
    "apple_watch",
    "garmin",
    "fitbit",
    "samsung_watch",
    "oura",
    "whoop",
    "withings",
    "other_scale",
    "bp_monitor",
    "glucose_monitor",
    "strava",
    "nike_run_club",
    "myfitnesspal",
    "cronometer",
    "healthifyme",
]

DAY_ORDER: list[str] = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

DisplayName = Annotated[str, Field(min_length=1, max_length=50)]
HeightCm = Annotated[float, Field(ge=50, le=260)]
ShortTag = Annotated[str, Field(min_length=1, max_length=40)]


def _unique(values: list[str]) -> list[str]:
    """Remove duplicates, keeping the first occurrence."""
    return list(dict.fromkeys(values))


# --- What the API returns --------------------------------------------------


class ProfileDetails(BaseModel):
    display_name: str
    date_of_birth: date | None
    sex: Sex | None
    height_cm: float | None
    goals: list[Goal]
    goals_notes: str | None
    goal_metric: GoalMetric | None
    injuries_notes: str | None
    water_target_ml: int
    data_sources: list[DataSource]
    data_sources_other: str | None
    onboarded: bool


class TrainingPreferences(BaseModel):
    equipment: list[Equipment]
    available_days: list[Day]
    minutes_per_session: int | None
    location: Location | None


class DietPreferences(BaseModel):
    diet_type: DietType | None
    cuisines: list[str]
    allergies: list[str]
    dislikes: list[str]
    meals_per_day: int | None
    cooking_minutes: int | None


class DisplaySettings(BaseModel):
    show_weight: bool
    show_calorie_intake: bool
    show_calories_burned: bool


class ProfileSettings(BaseModel):
    """Everything on the Settings / Profile page for one person."""

    profile_id: str
    # False when viewing the other person's profile: the page is read-only.
    can_edit: bool
    profile: ProfileDetails
    training: TrainingPreferences
    diet: DietPreferences
    display: DisplaySettings


# --- What the API accepts (only the fields sent are changed) ----------------


class ProfileDetailsUpdate(BaseModel):
    display_name: DisplayName | None = None
    date_of_birth: date | None = None
    sex: Sex | None = None
    height_cm: HeightCm | None = None
    goals: list[Goal] | None = None
    goals_notes: Annotated[str, Field(max_length=500)] | None = None
    goal_metric: GoalMetric | None = None
    injuries_notes: Annotated[str, Field(max_length=1000)] | None = None
    water_target_ml: Annotated[int, Field(ge=500, le=8000)] | None = None
    data_sources: list[DataSource] | None = None
    data_sources_other: Annotated[str, Field(max_length=200)] | None = None

    @field_validator("date_of_birth")
    @classmethod
    def plausible_age(cls, value: date | None) -> date | None:
        if value is None:
            return value
        today = date.today()
        age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
        if not 13 <= age <= 100:
            raise ValueError("age must be between 13 and 100")
        return value

    @field_validator("goals", "data_sources")
    @classmethod
    def unique_choices(cls, value: list[str] | None) -> list[str] | None:
        return _unique(value) if value is not None else value


class TrainingPreferencesUpdate(BaseModel):
    equipment: list[Equipment] | None = None
    available_days: list[Day] | None = None
    minutes_per_session: Annotated[int, Field(ge=5, le=300)] | None = None
    location: Location | None = None

    @field_validator("equipment")
    @classmethod
    def unique_equipment(cls, value: list[str] | None) -> list[str] | None:
        return _unique(value) if value is not None else value

    @field_validator("available_days")
    @classmethod
    def days_in_week_order(cls, value: list[str] | None) -> list[str] | None:
        return sorted(set(value), key=DAY_ORDER.index) if value is not None else value


class DietPreferencesUpdate(BaseModel):
    diet_type: DietType | None = None
    cuisines: Annotated[list[ShortTag], Field(max_length=20)] | None = None
    allergies: Annotated[list[ShortTag], Field(max_length=20)] | None = None
    dislikes: Annotated[list[ShortTag], Field(max_length=30)] | None = None
    meals_per_day: Annotated[int, Field(ge=1, le=8)] | None = None
    cooking_minutes: Annotated[int, Field(ge=0, le=240)] | None = None

    # Runs before the length checks, so blank entries are dropped instead of rejected.
    @field_validator("cuisines", "allergies", "dislikes", mode="before")
    @classmethod
    def tidy_tags(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        tags = [tag.strip() for tag in value if isinstance(tag, str) and tag.strip()]
        return _unique(tags)


class DisplaySettingsUpdate(BaseModel):
    show_weight: bool | None = None
    show_calorie_intake: bool | None = None
    show_calories_burned: bool | None = None
