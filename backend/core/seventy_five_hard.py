"""75 Hard: working out the current day, resets and completion from the ticks.

Nothing runs at midnight. Every time the page loads, the state is calculated
from the challenge start and the ticked items:

* A day is complete when all six items are ticked.
* Yesterday stays open (tickable) until 12:00 local time, so a forgotten tick
  doesn't restart the challenge. After that it's closed.
* A closed day that isn't complete restarts the count: the next day is Day 1.
* Reaching Day 75 with every item ticked completes the challenge.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.models.seventy_five_hard import (
    ITEMS,
    TOTAL_DAYS,
    ChecklistItem,
    DayChecklist,
    SeventyFiveHardState,
)
from core.supabase import SupabaseClient

GRACE_UNTIL = time(12, 0)


@dataclass(frozen=True)
class Challenge:
    id: str
    started_on: date
    start_day: int
    timezone: str


class NoRunningChallengeError(Exception):
    pass


class ChallengeAlreadyRunningError(Exception):
    pass


class DayNotEditableError(Exception):
    pass


class UnknownTimezoneError(Exception):
    pass


def local_now(timezone: str, now_utc: datetime | None = None) -> datetime:
    try:
        zone = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise UnknownTimezoneError(timezone) from error
    return (now_utc or datetime.now(UTC)).astimezone(zone)


def _checklist(day_date: date, day: int, ticked: set[str], editable: bool) -> DayChecklist:
    return DayChecklist(
        date=day_date,
        day=day,
        items=[ChecklistItem(item=item, checked=item in ticked) for item in ITEMS],  # type: ignore[arg-type]
        editable=editable,
    )


def calculate_state(
    challenge: Challenge | None,
    ticks: dict[date, set[str]],
    now_local: datetime,
    can_edit: bool,
) -> SeventyFiveHardState:
    """The page state, from the challenge start, the ticks per date and the local time."""
    if challenge is None:
        return SeventyFiveHardState(can_edit=can_edit, status="not_started")

    today = now_local.date()
    yesterday = today - timedelta(days=1)
    grace_open = now_local.time() < GRACE_UNTIL
    # Days up to and including this one can no longer be ticked.
    last_closed = yesterday - timedelta(days=1) if grace_open else yesterday

    def complete(day_date: date) -> bool:
        return set(ITEMS) <= ticks.get(day_date, set())

    # The current run: the date it started, and which day number that was.
    run_start, run_start_day = challenge.started_on, challenge.start_day
    last_missed_on: date | None = None

    day_date = challenge.started_on
    while day_date <= today:
        day = run_start_day + (day_date - run_start).days
        if complete(day_date):
            if day >= TOTAL_DAYS:
                return SeventyFiveHardState(
                    can_edit=can_edit,
                    status="completed",
                    day=TOTAL_DAYS,
                    last_missed_on=last_missed_on,
                    completed_on=day_date,
                )
        elif day_date <= last_closed:
            # Missed: start again at Day 1 the next day.
            last_missed_on = day_date
            run_start, run_start_day = day_date + timedelta(days=1), 1
        day_date += timedelta(days=1)

    today_day = run_start_day + (today - run_start).days
    yesterday_checklist = None
    if grace_open and yesterday >= run_start:
        yesterday_checklist = _checklist(
            yesterday, today_day - 1, ticks.get(yesterday, set()), editable=can_edit
        )

    return SeventyFiveHardState(
        can_edit=can_edit,
        status="active",
        day=today_day,
        today=_checklist(today, today_day, ticks.get(today, set()), editable=can_edit),
        yesterday=yesterday_checklist,
        last_missed_on=last_missed_on,
    )


def editable_dates(state: SeventyFiveHardState) -> set[date]:
    days = [state.today, state.yesterday] if state.status == "active" else []
    return {day.date for day in days if day is not None and day.editable}


# --- Reading and writing through Supabase (the user's own token) -------------


async def _running_challenge(
    supabase: SupabaseClient, token: str, profile_id: str
) -> Challenge | None:
    rows = await supabase.select(
        "challenges",
        {
            "select": "id,started_on,start_day,timezone",
            "profile_id": f"eq.{profile_id}",
            "stopped_at": "is.null",
        },
        token,
    )
    if not rows:
        return None
    row = rows[0]
    return Challenge(
        id=row["id"],
        started_on=date.fromisoformat(row["started_on"]),
        start_day=row["start_day"],
        timezone=row["timezone"],
    )


async def _ticks(
    supabase: SupabaseClient, token: str, profile_id: str, since: date
) -> dict[date, set[str]]:
    rows = await supabase.select(
        "challenge_checks",
        {
            "select": "date,item",
            "profile_id": f"eq.{profile_id}",
            "date": f"gte.{since.isoformat()}",
        },
        token,
    )
    ticks: dict[date, set[str]] = {}
    for row in rows:
        ticks.setdefault(date.fromisoformat(row["date"]), set()).add(row["item"])
    return ticks


async def get_state(
    supabase: SupabaseClient, token: str, profile_id: str, can_edit: bool
) -> SeventyFiveHardState:
    challenge = await _running_challenge(supabase, token, profile_id)
    if challenge is None:
        return calculate_state(None, {}, datetime.now(UTC), can_edit)
    ticks = await _ticks(supabase, token, profile_id, challenge.started_on)
    return calculate_state(challenge, ticks, local_now(challenge.timezone), can_edit)


async def start(
    supabase: SupabaseClient, token: str, profile_id: str, current_day: int, timezone: str
) -> SeventyFiveHardState:
    if await _running_challenge(supabase, token, profile_id) is not None:
        raise ChallengeAlreadyRunningError
    today = local_now(timezone).date()
    await supabase.insert(
        "challenges",
        {
            "profile_id": profile_id,
            "started_on": today.isoformat(),
            "start_day": current_day,
            "timezone": timezone,
        },
        token,
    )
    return await get_state(supabase, token, profile_id, can_edit=True)


async def stop(supabase: SupabaseClient, token: str, profile_id: str) -> SeventyFiveHardState:
    challenge = await _running_challenge(supabase, token, profile_id)
    if challenge is None:
        raise NoRunningChallengeError
    await supabase.update(
        "challenges",
        {"id": f"eq.{challenge.id}"},
        {"stopped_at": datetime.now(UTC).isoformat()},
        token,
    )
    return await get_state(supabase, token, profile_id, can_edit=True)


async def set_check(
    supabase: SupabaseClient,
    token: str,
    profile_id: str,
    day_date: date,
    item: str,
    checked: bool,
) -> SeventyFiveHardState:
    state = await get_state(supabase, token, profile_id, can_edit=True)
    if state.status != "active":
        raise NoRunningChallengeError
    if day_date not in editable_dates(state):
        raise DayNotEditableError
    if checked:
        await supabase.upsert(
            "challenge_checks",
            {"profile_id": profile_id, "date": day_date.isoformat(), "item": item},
            on_conflict="profile_id,date,item",
            access_token=token,
        )
    else:
        await supabase.delete(
            "challenge_checks",
            {
                "profile_id": f"eq.{profile_id}",
                "date": f"eq.{day_date.isoformat()}",
                "item": f"eq.{item}",
            },
            token,
        )
    return await get_state(supabase, token, profile_id, can_edit=True)
