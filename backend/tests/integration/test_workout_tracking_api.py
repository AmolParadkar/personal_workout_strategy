"""Doing workouts and changing plans, against the real Supabase project: logging
sets, finishing with an effort rating, the streak, progress kept when a plan is
replaced, plan changes with previews, core lifts, and access rules. Plans are
made by the rules alone (no LLM), so Groq's limits don't matter here.

RUN_SUPABASE_TESTS=1 uv run pytest tests/integration -v
"""

import os
import secrets
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api.main import app
from core.workouts import changes as change_service
from core.workouts import generate as generator
from core.workouts import plans as plan_service
from tests.integration.supabase_client import CONFIGURED, PUBLISHABLE_KEY, SECRET_KEY, call

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_SUPABASE_TESTS") != "1" or not CONFIGURED,
    reason="Set RUN_SUPABASE_TESTS=1 (and fill in the .env files) to run against Supabase",
)

client = TestClient(app)
TODAY = datetime.now(UTC).date()
MONDAY = TODAY - timedelta(days=TODAY.weekday())
EVERY_DAY = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


@pytest.fixture(autouse=True)
def rules_only_plans(monkeypatch):
    async def rules_plan(inputs, http, llm, reason, rules_only_if_llm_fails=True):
        return await generator.build_plan(inputs, None, None, reason)

    monkeypatch.setattr(plan_service, "build_plan", rules_plan)
    monkeypatch.setattr(change_service, "build_plan", rules_plan)


@pytest.fixture(scope="module")
def people():
    user_ids: list[str] = []
    people: dict[str, dict] = {}
    try:
        for name in ("a", "b"):
            password = secrets.token_urlsafe(16)
            email = f"track-test-{name}-{secrets.token_hex(3)}@example.com"
            status, user = call(
                "POST",
                "/auth/v1/admin/users",
                SECRET_KEY,
                body={"email": email, "password": password, "email_confirm": True},
            )
            assert status == 200, user
            user_ids.append(user["id"])
            status, session = call(
                "POST",
                "/auth/v1/token?grant_type=password",
                PUBLISHABLE_KEY,
                body={"email": email, "password": password},
            )
            assert status == 200, session
            token = session["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            profiles = client.get("/api/me/profiles", headers=headers).json()["profiles"]
            own = next(p for p in profiles if p["is_own"])
            people[name] = {"headers": headers, "token": token, "profile_id": own["id"]}
        a = people["a"]
        training = {
            "available_days": EVERY_DAY,
            "minutes_per_session": 40,
            "location": "home",
            "equipment": ["dumbbells", "resistance_bands"],
            "experience": "intermediate",
            # Goblet squat needs a kettlebell, which this person doesn't have.
            "core_exercises": ["Dumbbell_Squat", "Bent_Over_Two-Dumbbell_Row", "Goblet_Squat"],
        }
        response = client.patch("/api/me/settings/training", json=training, headers=a["headers"])
        assert response.status_code == 200, response.text
        assert response.json()["training"]["core_exercises"] == training["core_exercises"]
        week = client.post(
            "/api/me/workout-plan/generate",
            json={"today": TODAY.isoformat(), "reason": "new_week"},
            headers=a["headers"],
        ).json()
        assert week["active"], week
        a["plan"] = week["active"]
        yield people
    finally:
        for user_id in user_ids:
            call("DELETE", f"/auth/v1/admin/users/{user_id}", SECRET_KEY)


def today_workout(person, owner=None):
    owner = owner or person
    response = client.get(
        f"/api/profiles/{owner['profile_id']}/workout-today?day={TODAY.isoformat()}",
        headers=person["headers"],
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_unknown_core_lift_is_refused(people):
    response = client.patch(
        "/api/me/settings/training",
        json={"core_exercises": ["Made_Up_Lift"]},
        headers=people["a"]["headers"],
    )
    assert response.status_code == 422


def test_core_lifts_are_in_this_weeks_plan(people):
    mains = {
        i["exercise_id"]
        for s in people["a"]["plan"]["sessions"]
        for i in s["items"]
        if i["phase"] == "main"
    }
    assert {"Dumbbell_Squat", "Bent_Over_Two-Dumbbell_Row"} <= mains
    assert "Goblet_Squat" not in mains
    assert "Left out of your core lifts: Goblet Squat" in people["a"]["plan"]["rationale"]
    assert people["a"]["plan"]["block_start"] == MONDAY.isoformat()


def test_core_lift_options_are_doable_compound_lifts(people):
    options = client.get(
        f"/api/me/core-lift-options?today={TODAY.isoformat()}&search=squat",
        headers=people["a"]["headers"],
    ).json()
    names = [o["name"] for o in options]
    assert options and all("squat" in n.lower() for n in names)
    assert "Goblet Squat" not in names and all(o["equipment"] != "barbell" for o in options)


def test_todays_workout_and_logging_sets(people):
    a = people["a"]
    today = today_workout(a)
    assert today["has_plan"] and today["session"]["day"] == TODAY.isoformat()
    main = next(i for i in today["session"]["items"] if i["phase"] == "main")
    a["main_item"] = main
    first = client.put(
        "/api/me/exercise-logs",
        json={"session_item_id": main["id"], "set_number": 1, "reps": 10, "load_kg": 20},
        headers=a["headers"],
    )
    assert first.status_code == 200, first.text
    corrected = client.put(
        "/api/me/exercise-logs",
        json={"session_item_id": main["id"], "set_number": 1, "reps": 12, "load_kg": 20},
        headers=a["headers"],
    ).json()
    assert corrected["id"] == first.json()["id"] and corrected["reps"] == 12
    for set_number in (2, 3):
        client.put(
            "/api/me/exercise-logs",
            json={
                "session_item_id": main["id"],
                "set_number": set_number,
                "reps": 12,
                "load_kg": 20,
            },
            headers=a["headers"],
        )
    logs = today_workout(a)["logs"]
    assert [(log["set_number"], log["reps"]) for log in logs] == [(1, 12), (2, 12), (3, 12)]


def test_others_cannot_log_or_finish_my_workout(people):
    a, b = people["a"], people["b"]
    item_id = a["main_item"]["id"]
    refused = client.put(
        "/api/me/exercise-logs",
        json={"session_item_id": item_id, "set_number": 4, "reps": 1},
        headers=b["headers"],
    )
    assert refused.status_code == 404
    session_id = today_workout(a)["session"]["id"]
    assert (
        client.post(
            f"/api/me/sessions/{session_id}/complete",
            json={"done_on": TODAY.isoformat(), "effort": "easy"},
            headers=b["headers"],
        ).status_code
        == 404
    )
    seen = today_workout(b, owner=a)
    assert seen["can_edit"] is False and len(seen["logs"]) == 3


def test_finishing_with_effort_and_the_streak(people):
    a = people["a"]
    session_id = today_workout(a)["session"]["id"]
    done = client.post(
        f"/api/me/sessions/{session_id}/complete",
        json={"done_on": TODAY.isoformat(), "effort": "right"},
        headers=a["headers"],
    ).json()
    assert done["completion"]["effort"] == "right" and done["streak"] == 1
    rerated = client.post(
        f"/api/me/sessions/{session_id}/complete",
        json={"done_on": TODAY.isoformat(), "effort": "easy"},
        headers=a["headers"],
    ).json()
    assert rerated["completion"]["effort"] == "easy" and rerated["streak"] == 1


def test_a_change_previews_and_keeps_todays_progress(people):
    a = people["a"]
    remaining = [s["day"] for s in a["plan"]["sessions"] if s["day"] > TODAY.isoformat()]
    if not remaining:
        pytest.skip("No later training day left this week")
    day_off = remaining[0]
    week = client.post(
        "/api/me/workout-plan/changes",
        json={"kind": "day_off", "start_date": day_off, "today": TODAY.isoformat()},
        headers=a["headers"],
    ).json()
    assert week["draft"], week
    assert day_off not in {s["day"] for s in week["draft"]["sessions"]}
    assert any(c["status"] == "pending" and c["kind"] == "day_off" for c in week["changes"])
    applied = client.post(
        f"/api/me/workout-plans/{week['draft']['id']}/apply", headers=a["headers"]
    ).json()
    assert applied["draft"] is None
    assert any(c["status"] == "applied" for c in applied["changes"])
    # Today's logged sets and completion moved to the new plan.
    today = today_workout(a)
    assert today["completion"]["effort"] == "easy" and len(today["logs"]) == 3


def test_a_discarded_change_is_dropped(people):
    a = people["a"]
    week = client.post(
        "/api/me/workout-plan/changes",
        json={"kind": "medical", "start_date": TODAY.isoformat(), "today": TODAY.isoformat()},
        headers=a["headers"],
    ).json()
    assert week["draft"]
    after = client.delete(
        f"/api/me/workout-plans/{week['draft']['id']}", headers=a["headers"]
    ).json()
    assert not any(c["kind"] == "medical" for c in after["changes"])


def test_medical_pause_then_im_back(people):
    a = people["a"]
    week = client.post(
        "/api/me/workout-plan/changes",
        json={"kind": "medical", "start_date": TODAY.isoformat(), "today": TODAY.isoformat()},
        headers=a["headers"],
    ).json()
    paused = client.post(
        f"/api/me/workout-plans/{week['draft']['id']}/apply", headers=a["headers"]
    ).json()
    medical = next(c for c in paused["changes"] if c["kind"] == "medical")
    assert medical["can_end"]
    future = [s for s in paused["active"]["sessions"] if s["day"] > TODAY.isoformat()]
    assert not future  # nothing planned while paused
    back = client.post(
        f"/api/me/plan-changes/{medical['id']}/end",
        json={"today": TODAY.isoformat()},
        headers=a["headers"],
    ).json()
    assert back["draft"] and "Welcome back" in back["message"]


def test_vacation_next_week_is_saved_for_later(people):
    a = people["a"]
    start = MONDAY + timedelta(days=7)
    week = client.post(
        "/api/me/workout-plan/changes",
        json={
            "kind": "vacation",
            "start_date": start.isoformat(),
            "end_date": (start + timedelta(days=3)).isoformat(),
            "vacation_mode": "travel",
            "today": TODAY.isoformat(),
        },
        headers=a["headers"],
    ).json()
    assert "that week's plan" in week["message"]
    _, rows = call(
        "GET",
        f"/rest/v1/plan_changes?select=status&profile_id=eq.{a['profile_id']}&kind=eq.vacation",
        SECRET_KEY,
    )
    assert rows[0]["status"] == "applied"


def test_bad_change_is_explained(people):
    response = client.post(
        "/api/me/workout-plan/changes",
        json={"kind": "shorter", "start_date": TODAY.isoformat(), "today": TODAY.isoformat()},
        headers=people["a"]["headers"],
    )
    assert response.status_code == 422 and "minutes" in response.json()["detail"]


def test_only_own_changes(people):
    b = people["b"]
    status, _ = call(
        "POST",
        "/rest/v1/plan_changes",
        PUBLISHABLE_KEY,
        b["token"],
        {
            "profile_id": people["a"]["profile_id"],
            "kind": "day_off",
            "start_date": TODAY.isoformat(),
        },
    )
    assert status in (401, 403)


def test_signed_out_visitors_see_nothing():
    status, rows = call("GET", "/rest/v1/plan_changes?select=id", PUBLISHABLE_KEY)
    assert status in (401, 403) or rows == []
