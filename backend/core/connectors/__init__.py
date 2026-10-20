"""Direct connectors to health services (context/data-sources.md)."""

from core.connectors.base import Connector
from core.connectors.oura import OuraConnector
from core.connectors.polar import PolarConnector
from core.connectors.whoop import WhoopConnector
from core.connectors.withings import WithingsConnector

CONNECTORS: dict[str, Connector] = {
    connector.service: connector
    for connector in (WithingsConnector(), OuraConnector(), WhoopConnector(), PolarConnector())
}

# May this source's data be sent to the LLM when building plans? Only once the
# service's terms have been checked (context/data-sources.md). Apple Health and
# typed-in values are the person's own.
AI_ALLOWED: dict[str, bool] = {
    "apple_health": True,
    "manual": True,
    "withings": False,
    "oura": False,
    "whoop": False,
    "polar": False,
}

# When several sources send the same metric for a day, pages use the first one
# in this order: the specialist device first, then anything else.
_SLEEP = ["oura", "whoop", "withings", "polar", "apple_health"]
SOURCE_PREFERENCE: dict[str, list[str]] = {
    "weight_kg": ["manual", "withings", "apple_health"],
    "body_fat_pct": ["withings", "apple_health"],
    "muscle_mass_kg": ["withings", "apple_health"],
    "systolic_mmhg": ["withings", "apple_health"],
    "diastolic_mmhg": ["withings", "apple_health"],
    "steps": ["apple_health", "polar", "oura", "whoop", "withings"],
    "active_energy_kcal": ["apple_health", "polar", "oura", "withings"],
    "walking_running_km": ["apple_health", "polar", "withings"],
    "resting_hr": ["whoop", "oura", "apple_health"],
    "hrv_ms": ["whoop", "oura", "polar", "apple_health"],
    **{
        metric: _SLEEP
        for metric in (
            "bedtime",
            "wake_time",
            "sleep_in_bed_minutes",
            "sleep_asleep_minutes",
            "sleep_deep_minutes",
            "sleep_rem_minutes",
            "sleep_light_minutes",
            "sleep_score",
        )
    },
}


def preferred(metric: str, rows: list[dict]) -> dict | None:
    """Of one day's rows for a metric (each with `source`), the one pages should show."""
    order = SOURCE_PREFERENCE.get(metric, [])
    rank = {source: index for index, source in enumerate(order)}
    return min(rows, key=lambda row: rank.get(row["source"], len(order)), default=None)
