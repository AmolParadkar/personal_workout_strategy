"""Rules for counting 75 Hard days (core/seventy_five_hard.py)."""

from datetime import UTC, date, datetime, timedelta

import pytest

from core.models.seventy_five_hard import ITEMS
from core.seventy_five_hard import (
    Challenge,
    UnknownTimezoneError,
    calculate_state,
    editable_dates,
    local_now,
)

ALL = set(ITEMS)
START = date(2026, 10, 1)


def at(day: date, hour: int) -> datetime:
    """A local time on a given date."""
    return datetime(day.year, day.month, day.day, hour, 0)


def challenge(start_day: int = 1, started_on: date = START) -> Challenge:
    return Challenge(id="c1", started_on=started_on, start_day=start_day, timezone="UTC")


def complete_days(first: date, count: int) -> dict[date, set[str]]:
    return {first + timedelta(days=i): set(ALL) for i in range(count)}


def test_no_challenge_means_not_started():
    state = calculate_state(None, {}, at(START, 9), can_edit=True)
    assert state.status == "not_started"
    assert state.day is None


def test_first_day_uses_the_day_you_said_you_were_on():
    state = calculate_state(challenge(start_day=12), {}, at(START, 9), can_edit=True)
    assert state.status == "active"
    assert state.day == 12
    assert state.today.date == START
    assert [i.item for i in state.today.items] == ITEMS
    assert state.yesterday is None  # nothing before the start date


def test_days_count_up_while_every_day_is_complete():
    ticks = complete_days(START, 4)
    state = calculate_state(challenge(), ticks, at(START + timedelta(days=4), 15), can_edit=True)
    assert state.day == 5
    assert state.last_missed_on is None


def test_yesterday_stays_open_until_noon():
    today = START + timedelta(days=1)
    morning = calculate_state(challenge(), {}, at(today, 11), can_edit=True)
    assert morning.day == 2
    assert morning.yesterday is not None
    assert morning.yesterday.day == 1
    assert editable_dates(morning) == {START, today}


def test_incomplete_yesterday_restarts_at_noon():
    today = START + timedelta(days=1)
    ticks = {START: ALL - {"reading"}}
    afternoon = calculate_state(challenge(start_day=30), ticks, at(today, 12), can_edit=True)
    assert afternoon.day == 1
    assert afternoon.last_missed_on == START
    assert afternoon.yesterday is None
    assert editable_dates(afternoon) == {today}


def test_ticking_yesterday_before_noon_saves_the_streak():
    today = START + timedelta(days=1)
    ticks = {START: set(ALL)}
    state = calculate_state(challenge(start_day=30), ticks, at(today, 13), can_edit=True)
    assert state.day == 31
    assert state.last_missed_on is None


def test_missed_day_in_the_middle_restarts_the_next_day_as_day_one():
    ticks = complete_days(START, 10)
    del ticks[START + timedelta(days=5)]  # day 6 missed
    today = START + timedelta(days=10)
    state = calculate_state(challenge(), ticks, at(today, 15), can_edit=True)
    # Days 7..10 of the old count become days 1..4; today is day 5.
    assert state.last_missed_on == START + timedelta(days=5)
    assert state.day == 5


def test_several_days_away_restarts_today_as_day_one():
    today = START + timedelta(days=5)
    state = calculate_state(challenge(start_day=40), {}, at(today, 15), can_edit=True)
    assert state.day == 1
    assert state.last_missed_on == today - timedelta(days=1)


def test_reaching_day_75_completes_the_challenge():
    ticks = complete_days(START, 3)
    state = calculate_state(challenge(start_day=73), ticks, at(START + timedelta(days=2), 21), True)
    assert state.status == "completed"
    assert state.completed_on == START + timedelta(days=2)
    assert editable_dates(state) == set()


def test_day_75_not_yet_complete_is_still_active():
    state = calculate_state(challenge(start_day=75), {START: {"diet"}}, at(START, 21), True)
    assert state.status == "active"
    assert state.day == 75


def test_ticks_show_on_the_checklist():
    ticks = {START: {"water", "reading"}}
    state = calculate_state(challenge(), ticks, at(START, 9), can_edit=True)
    checked = {i.item for i in state.today.items if i.checked}
    assert checked == {"water", "reading"}


def test_other_persons_challenge_is_view_only():
    state = calculate_state(challenge(), {}, at(START + timedelta(days=1), 9), can_edit=False)
    assert state.today.editable is False
    assert state.yesterday.editable is False
    assert editable_dates(state) == set()


def test_local_time_follows_the_challenge_timezone():
    utc = datetime(2026, 10, 1, 20, 0, tzinfo=UTC)  # 20:00 UTC = 01:30 next day in India
    assert local_now("Asia/Kolkata", utc).date() == date(2026, 10, 2)
    assert local_now("UTC", utc).date() == date(2026, 10, 1)


def test_unknown_timezone_is_rejected():
    with pytest.raises(UnknownTimezoneError):
        local_now("Mars/Olympus_Mons")
