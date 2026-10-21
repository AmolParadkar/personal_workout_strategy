"""M6 part 2: progressive overload, core lifts, 6-week blocks, plan changes,
logging history and the streak (core/workouts/)."""

import asyncio
from datetime import date, timedelta

import pytest

from core.models.workouts import PlanChangeRequest
from core.workouts import changes, generate, inputs, overload, tracking
from tests.test_workouts import LIBRARY
from tests.test_workouts import inputs as base_inputs

MON = date(2026, 10, 19)
LIB = {e["id"]: e for e in LIBRARY}


def run(coroutine):
    return asyncio.run(coroutine)


def main_ids(session):
    return [i["exercise_id"] for i in session["items"] if i["phase"] == "main"]


# --- Progressive overload ----------------------------------------------------------------


def item(exercise="Dumbbell_Bench_Press", low=8, high=12, sets=3):
    return {
        "phase": "main",
        "exercise_id": exercise,
        "sets": sets,
        "reps_min": low,
        "reps_max": high,
    }


def last(reps, kg, effort="right", low=8, high=12):
    return overload.LastTime(
        sets=[(r, kg) for r in reps], reps_min=low, reps_max=high, effort=effort
    )


def test_all_sets_at_the_top_add_a_step_of_weight():
    out = overload.next_target(item(), last([12, 12, 12], 20), LIB)
    assert out["target_load_kg"] == 22 and "try 22 kg" in out["notes"]


def test_in_range_keeps_the_weight_and_aims_for_more_reps():
    out = overload.next_target(item(), last([10, 9, 8], 20), LIB)
    assert out["target_load_kg"] == 20 and "more reps" in out["notes"]


def test_easy_session_progresses_even_below_the_top():
    out = overload.next_target(item(), last([9, 9, 8], 20, effort="easy"), LIB)
    assert out["target_load_kg"] == 22


def test_too_hard_or_mostly_short_goes_lighter_or_holds():
    short = overload.next_target(item(), last([6, 5, 8], 20), LIB)
    assert short["target_load_kg"] == 18
    hard = overload.next_target(item(), last([12, 12, 12], 20, effort="too_hard"), LIB)
    assert hard["target_load_kg"] == 20


def test_barbell_steps_are_bigger_and_bodyweight_adds_reps():
    barbell = overload.next_target(item("Barbell_Squat"), last([12, 12, 12], 60), LIB)
    assert barbell["target_load_kg"] == 62.5
    pushups = overload.next_target(item("Pushups"), last([12, 12, 12], None), LIB)
    assert (pushups["reps_min"], pushups["reps_max"]) == (10, 14)


def test_gentle_week_is_lighter_with_a_set_fewer():
    out = overload.next_target(item(sets=4), last([12, 12, 12], 20), LIB, gentle=True)
    assert out["sets"] == 3 and out["target_load_kg"] == 18.5
    assert out["notes"].startswith("Easing back in")


def test_no_history_leaves_the_item_alone():
    assert overload.next_target(item(), None, LIB) == item()


# --- Core lifts and blocks ------------------------------------------------------------------


def test_core_lifts_are_in_the_plan_every_week_on_matching_days():
    plan_inputs = base_inputs(
        available_days=["mon", "wed", "fri"], core_exercises=["Goblet_Squat", "Dumbbell_Row"]
    )
    plan = run(generate.build_plan(plan_inputs, None, None, "new_week"))
    days_with = {
        exercise: [s["day"] for s in plan["sessions"] if exercise in main_ids(s)]
        for exercise in ("Goblet_Squat", "Dumbbell_Row")
    }
    for days in days_with.values():
        assert 1 <= len(days) <= 2
        if len(days) == 2:
            assert (date.fromisoformat(days[1]) - date.fromisoformat(days[0])).days >= 2
    first = plan["sessions"][0]
    core_here = [e for e in main_ids(first) if e in ("Goblet_Squat", "Dumbbell_Row")]
    assert main_ids(first)[: len(core_here)] == core_here  # core lifts come first


def test_core_lifts_not_doable_with_the_equipment_are_left_out():
    plan = run(
        generate.build_plan(base_inputs(core_exercises=["Barbell_Squat"]), None, None, "new_week")
    )
    assert all("Barbell_Squat" not in main_ids(s) for s in plan["sessions"])


def test_within_a_block_last_weeks_picks_are_kept():
    first = run(generate.build_plan(base_inputs(), None, None, "requested"))
    by_focus = {}
    for s in first["sessions"]:
        by_focus.setdefault(s["focus"], []).extend(main_ids(s))
    next_week = base_inputs(
        week_start=MON + timedelta(weeks=1),
        today=MON + timedelta(weeks=1),
        block_main=by_focus,
        block_start=MON,
    )
    second = run(generate.build_plan(next_week, None, None, "new_week"))
    assert [main_ids(s) for s in second["sessions"]] == [main_ids(s) for s in first["sessions"]]
    assert second["block_start"] == MON.isoformat() and "Week 2 of 6" in second["rationale"]


def test_block_week_counts_from_the_block_start():
    assert (
        generate.block_week(base_inputs(week_start=MON + timedelta(weeks=5), block_start=MON)) == 6
    )
    assert generate.block_week(base_inputs()) == 1


def test_block_from_a_saved_plan_skips_core_lifts():
    plan = {
        "block_start": "2026-10-12",
        "workout_sessions": [
            {
                "day": "2026-10-12",
                "focus": "full_body",
                "session_items": [
                    {"phase": "main", "position": 1, "exercise_id": "Pushups"},
                    {"phase": "main", "position": 0, "exercise_id": "Goblet_Squat"},
                    {"phase": "cooldown", "position": 0, "exercise_id": "X"},
                ],
            }
        ],
    }
    start, by_focus = inputs.block_from_plan(plan, {"Goblet_Squat"})
    assert start == date(2026, 10, 12) and by_focus == {"full_body": ["Pushups"]}


# --- Changes ----------------------------------------------------------------------------------


def change(kind, start, end=None, **extra):
    return {
        "kind": kind,
        "start_date": start.isoformat(),
        "end_date": end.isoformat() if end else None,
        **extra,
    }


def test_changes_become_days_and_settings():
    adj = inputs.adjustments(
        [
            change("day_off", MON + timedelta(days=2), MON + timedelta(days=2)),
            change("add_session", MON + timedelta(days=5)),
            change("shorter", MON + timedelta(days=4), minutes=25),
            change(
                "vacation",
                MON + timedelta(days=6),
                MON + timedelta(days=12),
                vacation_mode="travel",
            ),
            change("cheat_meal", MON + timedelta(days=3), cheat_mode="spread"),
            change(
                "other",
                MON,
                details={"avoid_muscles": ["chest"], "easier": True, "summary": "Sore chest"},
            ),
        ],
        MON,
        MON,
    )
    assert adj.days_off == {MON + timedelta(days=2)}
    assert adj.extra_days == {MON + timedelta(days=5)}
    assert adj.minutes == {MON + timedelta(days=4): 25}
    assert adj.travel_days == {MON + timedelta(days=6)}
    assert adj.spread_after == [MON + timedelta(days=3)]
    assert adj.avoid_muscles == {"chest"} and adj.gentle and "Sore chest" in adj.notes


def test_medical_pause_and_gentle_first_week_back():
    paused = inputs.adjustments([change("medical", MON + timedelta(days=1))], MON, MON)
    assert paused.days_off == {MON + timedelta(days=d) for d in range(1, 7)} and not paused.gentle
    back = inputs.adjustments(
        [change("medical", MON - timedelta(days=10), MON - timedelta(days=2))], MON, MON
    )
    assert back.gentle and not back.days_off


def test_days_off_and_extra_days_reshape_the_week():
    adj = generate.Adjustments(
        days_off={MON + timedelta(days=2)}, extra_days={MON + timedelta(days=5)}
    )
    plan = run(generate.build_plan(base_inputs(adjustments=adj), None, None, "change"))
    assert [s["day"] for s in plan["sessions"]] == ["2026-10-19", "2026-10-23", "2026-10-24"]


def test_travel_days_use_bodyweight_and_bands_only():
    adj = generate.Adjustments(travel_days={MON})
    plan = run(generate.build_plan(base_inputs(adjustments=adj), None, None, "change"))
    travel = plan["sessions"][0]
    for item_ in travel["items"]:
        assert LIB[item_["exercise_id"]]["equipment"] in (None, "body only", "bands")
    assert "travel" in travel["explanation"]


def test_cheat_meal_spreads_a_little_cardio_over_the_following_sessions():
    days = [MON, MON + timedelta(days=2), MON + timedelta(days=4)]
    assert generate.spread_cardio(days, [MON]) == {days[1]: 10, days[2]: 10}
    assert generate.spread_cardio(days, [MON + timedelta(days=4)]) == {days[2]: 10}
    adj = generate.Adjustments(spread_after=[MON])
    plan = run(generate.build_plan(base_inputs(adjustments=adj), None, None, "change"))
    assert plan["sessions"][1]["minutes"] == 45 + 10 and plan["sessions"][0]["minutes"] == 45


def test_shorter_day_and_avoided_muscles():
    adj = generate.Adjustments(minutes={MON: 20}, avoid_muscles={"chest"})
    plan = run(generate.build_plan(base_inputs(adjustments=adj), None, None, "change"))
    assert plan["sessions"][0]["minutes"] == 20
    for s in plan["sessions"]:
        for item_ in s["items"]:
            assert "chest" not in LIB[item_["exercise_id"]]["primary_muscles"]


def request(kind, start, **extra):
    return PlanChangeRequest(kind=kind, start_date=start, today=MON + timedelta(days=1), **extra)


def test_change_requests_are_checked():
    tue = MON + timedelta(days=1)
    training = {tue, MON + timedelta(days=3)}
    with pytest.raises(changes.ChangeError, match="today or a later"):
        changes.check_request(request("day_off", MON), training)
    with pytest.raises(changes.ChangeError, match="this week"):
        changes.check_request(request("day_off", MON + timedelta(days=9)), training)
    with pytest.raises(changes.ChangeError, match="already has a session"):
        changes.check_request(request("add_session", tue), training)
    with pytest.raises(changes.ChangeError, match="no session to shorten"):
        changes.check_request(request("shorter", MON + timedelta(days=2), minutes=20), training)
    with pytest.raises(changes.ChangeError, match="train while away"):
        changes.check_request(request("vacation", tue), training)
    with pytest.raises(changes.ChangeError, match="Spread"):
        changes.check_request(request("cheat_meal", tue), training)
    with pytest.raises(changes.ChangeError, match="Describe"):
        changes.check_request(request("other", tue, note="  "), training)
    ok = changes.check_request(request("day_off", tue), training)
    assert ok.end_date == tue
    later = changes.check_request(
        request(
            "vacation",
            MON + timedelta(days=14),
            end_date=MON + timedelta(days=20),
            vacation_mode="rest",
        ),
        training,
    )
    assert later.end_date == MON + timedelta(days=20)


def test_kept_days_go_first_and_replace_regenerated_ones():
    kept = [{"day": "2026-10-19", "title": "Done"}]
    plan = {
        "sessions": [{"day": "2026-10-19", "title": "New"}, {"day": "2026-10-21", "title": "Next"}]
    }
    merged = inputs.merge_kept(kept, plan)
    assert [s["title"] for s in merged["sessions"]] == ["Done", "Next"]


# --- History and streak ---------------------------------------------------------------------


def test_history_uses_the_most_recent_session_of_each_exercise():
    rows = [
        {
            "exercise_id": "Goblet_Squat",
            "session_item_id": "new",
            "reps": 12,
            "load_kg": 16,
            "session_items": {
                "reps_min": 8,
                "reps_max": 12,
                "workout_sessions": {"session_completions": [{"effort": "easy"}]},
            },
        },
        {
            "exercise_id": "Goblet_Squat",
            "session_item_id": "new",
            "reps": 11,
            "load_kg": 16,
            "session_items": {},
        },
        {
            "exercise_id": "Goblet_Squat",
            "session_item_id": "old",
            "reps": 8,
            "load_kg": 12,
            "session_items": {},
        },
    ]
    history = inputs.history_from_logs(rows)
    squat = history["Goblet_Squat"]
    assert squat.sets == [(12, 16.0), (11, 16.0)]


def session(day, done):
    return {"day": day.isoformat(), "session_completions": [{"id": "c"}] if done else []}


def test_streak_counts_planned_workouts_done_in_a_row():
    wed = MON + timedelta(days=2)
    sessions = [
        session(MON - timedelta(days=7), True),
        session(MON - timedelta(days=5), True),
        session(MON - timedelta(days=3), True),
        session(MON, True),
        session(MON + timedelta(days=1), False),  # this week, not done yet: no break
        session(wed, False),  # today
        session(wed + timedelta(days=2), False),  # future
    ]
    assert tracking.streak(sessions, wed) == 4
    broken = sessions + [session(MON - timedelta(days=4), False)]
    assert tracking.streak(broken, wed) == 2
    assert tracking.streak([], wed) == 0
