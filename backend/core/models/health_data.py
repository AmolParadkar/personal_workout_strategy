"""Health data intake: Apple Health samples, the connection token, water and weight."""

import re
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Metric = Literal[
    "steps",
    "active_energy_kcal",
    "walking_running_km",
    "sleep_in_bed_minutes",
    "sleep_asleep_minutes",
    "bedtime",
    "wake_time",
    "weight_kg",
    "resting_hr",
    "hrv_ms",
    "vo2_max",
]

# Sensible ranges, so a typo in the Shortcut can't store nonsense.
METRIC_RANGES: dict[str, tuple[float, float]] = {
    "steps": (0, 200_000),
    "active_energy_kcal": (0, 20_000),
    "walking_running_km": (0, 300),
    "sleep_in_bed_minutes": (0, 1440),
    "sleep_asleep_minutes": (0, 1440),
    "weight_kg": (20, 400),
    "resting_hr": (20, 250),
    "hrv_ms": (1, 500),
    "vo2_max": (5, 100),
}
# Recorded as a time, not a number.
TIME_METRICS = {"bedtime", "wake_time"}

GALLON_ML = 3785


class IngestSample(BaseModel):
    metric: Metric
    # The local day the value belongs to (for sleep: the morning you woke up).
    date: date
    value: float | None = None
    # Exact time, required for bedtime and wake time.
    at: datetime | None = None

    @field_validator("value", mode="before")
    @classmethod
    def accept_formatted_numbers(cls, value: object) -> object:
        # iOS Shortcuts may insert numbers as text with thousands separators or a
        # unit, e.g. "8,421" or "78.4 kg": keep the leading number.
        if isinstance(value, str):
            cleaned = value.replace(",", "").replace("\u00a0", " ").strip()
            match = re.match(r"-?\d+(\.\d+)?", cleaned)
            return float(match.group()) if match else (None if cleaned == "" else value)
        return value

    @model_validator(mode="after")
    def value_fits_metric(self) -> "IngestSample":
        if self.metric in TIME_METRICS:
            if self.at is None:
                raise ValueError(f"{self.metric} needs 'at' (a date and time)")
            return self
        if self.value is None:
            raise ValueError(f"{self.metric} needs a 'value'")
        low, high = METRIC_RANGES[self.metric]
        if not low <= self.value <= high:
            raise ValueError(f"{self.metric} must be between {low:g} and {high:g}")
        return self


class IngestRequest(BaseModel):
    # Checked one by one (see core.health_data.validate_samples), so one bad or
    # missing measurement doesn't stop the rest of the day's data being saved.
    samples: Annotated[list[dict[str, Any]], Field(min_length=1, max_length=500)]


class SkippedSample(BaseModel):
    index: int
    metric: str | None
    reason: str


class IngestResult(BaseModel):
    saved: int
    skipped: list[SkippedSample]


class HealthConnection(BaseModel):
    """Whether the person's iOS Shortcut is set up, and when data last arrived."""

    connected: bool
    created_at: datetime | None = None
    last_used_at: datetime | None = None
    latest_data_on: date | None = None


class NewHealthConnection(BaseModel):
    # Shown once: only a hash is stored.
    token: str
    created_at: datetime


class WaterLog(BaseModel):
    id: str
    ml: int
    logged_at: datetime


class WaterDay(BaseModel):
    date: date
    total_ml: int
    target_ml: int
    logs: list[WaterLog]
    can_edit: bool


class AddWater(BaseModel):
    ml: Annotated[int, Field(ge=1, le=2000)]
    # The person's local date (the browser knows it; the server doesn't).
    date: date


class WeightEntry(BaseModel):
    kg: float
    date: date
    source: Literal["apple_health", "manual"]


class WeightSummary(BaseModel):
    latest: WeightEntry | None
    can_edit: bool


class LogWeight(BaseModel):
    kg: Annotated[float, Field(ge=20, le=400)]
    date: date
