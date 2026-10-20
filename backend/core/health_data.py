"""Health data intake: the Apple Health connection, water and body weight."""

import hashlib
import secrets
from datetime import UTC, date, datetime, timedelta

from pydantic import ValidationError

from core import seventy_five_hard
from core.connectors import preferred
from core.models.health_data import (
    GALLON_ML,
    HealthConnection,
    IngestSample,
    NewHealthConnection,
    SkippedSample,
    WaterDay,
    WaterLog,
    WeightEntry,
    WeightSummary,
)
from core.supabase import SupabaseClient

TOKEN_PREFIX = "wst_"


class DateOutOfRangeError(Exception):
    """A date that can't be someone's local "today" (or yesterday)."""


def new_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    # Must match the database function public.ingest_health_samples.
    return hashlib.sha256(token.encode()).hexdigest()


def check_local_date(day: date, now_utc: datetime | None = None) -> None:
    """Local dates differ from UTC by at most a day either way."""
    today_utc = (now_utc or datetime.now(UTC)).date()
    if not today_utc - timedelta(days=1) <= day <= today_utc + timedelta(days=1):
        raise DateOutOfRangeError


# --- Apple Health connection -------------------------------------------------


def validate_samples(raw: list[dict]) -> tuple[list[IngestSample], list[SkippedSample]]:
    """Split the Shortcut's samples into valid ones and skipped ones (with reasons).
    A value of 0 for something that can't be 0 (e.g. weight) means "no data today"."""
    valid: list[IngestSample] = []
    skipped: list[SkippedSample] = []
    for index, item in enumerate(raw):
        metric = item.get("metric") if isinstance(item, dict) else None
        try:
            valid.append(IngestSample.model_validate(item))
        except ValidationError as error:
            reason = error.errors()[0]["msg"].removeprefix("Value error, ")
            skipped.append(SkippedSample(index=index, metric=metric, reason=reason))
    return valid, skipped


async def ingest(supabase: SupabaseClient, token: str, samples: list[IngestSample]) -> int:
    """Save samples sent by the iOS Shortcut. The token identifies the person."""
    return await supabase.rpc(
        "ingest_health_samples",
        {
            "token": token,
            "samples": [s.model_dump(mode="json", exclude_none=True) for s in samples],
        },
    )


async def get_connection(supabase: SupabaseClient, token: str, profile_id: str) -> HealthConnection:
    rows = await supabase.select(
        "ingest_tokens",
        {"select": "created_at,last_used_at", "profile_id": f"eq.{profile_id}"},
        token,
    )
    if not rows:
        return HealthConnection(connected=False)
    latest = await supabase.select(
        "health_samples",
        {
            "select": "recorded_on",
            "profile_id": f"eq.{profile_id}",
            "source": "eq.apple_health",
            "order": "recorded_on.desc",
            "limit": "1",
        },
        token,
    )
    return HealthConnection(
        connected=True,
        created_at=rows[0]["created_at"],
        last_used_at=rows[0]["last_used_at"],
        latest_data_on=latest[0]["recorded_on"] if latest else None,
    )


async def create_connection(
    supabase: SupabaseClient, token: str, profile_id: str
) -> NewHealthConnection:
    """Create a new connection token, replacing (and so cancelling) any old one."""
    await supabase.delete("ingest_tokens", {"profile_id": f"eq.{profile_id}"}, token)
    plain = new_token()
    rows = await supabase.insert(
        "ingest_tokens",
        {"profile_id": profile_id, "token_hash": hash_token(plain)},
        token,
        returning="created_at",
    )
    return NewHealthConnection(token=plain, created_at=rows[0]["created_at"])


async def remove_connection(supabase: SupabaseClient, token: str, profile_id: str) -> None:
    await supabase.delete("ingest_tokens", {"profile_id": f"eq.{profile_id}"}, token)


# --- Water ---------------------------------------------------------------------


async def get_water_day(
    supabase: SupabaseClient, token: str, profile_id: str, day: date, can_edit: bool
) -> WaterDay:
    logs = await supabase.select(
        "water_logs",
        {
            "select": "id,ml,logged_at",
            "profile_id": f"eq.{profile_id}",
            "logged_on": f"eq.{day.isoformat()}",
            "order": "logged_at",
        },
        token,
    )
    profile = await supabase.select(
        "profiles", {"select": "water_target_ml", "id": f"eq.{profile_id}"}, token
    )
    return WaterDay(
        date=day,
        total_ml=sum(log["ml"] for log in logs),
        target_ml=profile[0]["water_target_ml"],
        logs=[WaterLog(**log) for log in logs],
        can_edit=can_edit,
    )


async def add_water(
    supabase: SupabaseClient, token: str, profile_id: str, ml: int, day: date
) -> WaterDay:
    check_local_date(day)
    await supabase.insert(
        "water_logs", {"profile_id": profile_id, "ml": ml, "logged_on": day.isoformat()}, token
    )
    water = await get_water_day(supabase, token, profile_id, day, can_edit=True)
    if water.total_ml >= GALLON_ML:
        await _tick_75_hard_water(supabase, token, profile_id, day)
    return water


async def _tick_75_hard_water(
    supabase: SupabaseClient, token: str, profile_id: str, day: date
) -> None:
    """A gallon logged ticks the 75 Hard water item, if that day can still be ticked.
    It never unticks: the person may have ticked it themselves."""
    try:
        await seventy_five_hard.set_check(supabase, token, profile_id, day, "water", True)
    except (seventy_five_hard.NoRunningChallengeError, seventy_five_hard.DayNotEditableError):
        pass


async def undo_water(
    supabase: SupabaseClient, token: str, profile_id: str, log_id: str, day: date
) -> WaterDay:
    await supabase.delete(
        "water_logs", {"id": f"eq.{log_id}", "profile_id": f"eq.{profile_id}"}, token
    )
    return await get_water_day(supabase, token, profile_id, day, can_edit=True)


# --- Body weight ---------------------------------------------------------------


async def get_weight(
    supabase: SupabaseClient, token: str, profile_id: str, can_edit: bool
) -> WeightSummary:
    rows = await supabase.select(
        "health_samples",
        {
            "select": "value,recorded_on,source",
            "profile_id": f"eq.{profile_id}",
            "metric": "eq.weight_kg",
            "order": "recorded_on.desc,updated_at.desc",
            "limit": "10",
        },
        token,
    )
    # The latest day's weigh-in, from the preferred source if several sent one.
    row = (
        preferred("weight_kg", [r for r in rows if r["recorded_on"] == rows[0]["recorded_on"]])
        if rows
        else None
    )
    latest = (
        WeightEntry(kg=float(row["value"]), date=row["recorded_on"], source=row["source"])
        if row
        else None
    )
    return WeightSummary(latest=latest, can_edit=can_edit)


async def log_weight(
    supabase: SupabaseClient, token: str, profile_id: str, kg: float, day: date
) -> WeightSummary:
    check_local_date(day)
    filters = {
        "profile_id": f"eq.{profile_id}",
        "metric": "eq.weight_kg",
        "recorded_on": f"eq.{day.isoformat()}",
        "source": "eq.manual",
    }
    values = {"value": kg, "recorded_at": datetime.now(UTC).isoformat()}
    # One manual weight per day: correct today's if it exists, otherwise add it.
    updated = await supabase.update("health_samples", filters, values, token)
    if not updated:
        await supabase.insert(
            "health_samples",
            {
                "profile_id": profile_id,
                "metric": "weight_kg",
                "recorded_on": day.isoformat(),
                "source": "manual",
                **values,
            },
            token,
        )
    return await get_weight(supabase, token, profile_id, can_edit=True)
