"""Weekly workout plans against the real Supabase project: saving, previews,
swaps and access rules. Plans are made by the rules alone here (no LLM), so the
tests don't depend on Groq's per-minute limits; the LLM part is covered by
tests/test_workouts.py.

RUN_SUPABASE_TESTS=1 uv run pytest tests/integration -v
"""

import os
import secrets
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api.main import app
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
    """Make plans straight away with the rules, as if the LLM had answered."""

    async def rules_plan(inputs, http, llm, reason, rules_only_if_llm_fails=True):
        return await generator.build_plan(inputs, None, None, reason)

    monkeypatch.setattr(plan_service, "build_plan", rules_plan)


@pytest.fixture(scope="module")
def people():
    user_ids: list[str] = []
    people: dict[str, dict] = {}
    try:
        for name in ("a", "b"):
            password = secrets.token_urlsafe(16)
            email = f"plan-test-{name}-{secrets.token_hex(3)}@example.com"
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
        client.patch(
            "/api/me/settings/profile",
            json={"goals": ["build_muscle"], "injuries_notes": "Sore left knee"},
            headers=a["headers"],
        )
        training = {
            "available_days": EVERY_DAY,  # so there are days left whatever today is
            "minutes_per_session": 40,
            "location": "home",
            "equipment": ["dumbbells", "resistance_bands"],
            "experience": "intermediate",
        }
        response = client.patch("/api/me/settings/training", json=training, headers=a["headers"])
        assert response.status_code == 200, response.text
        assert response.json()["training"]["experience"] == "intermediate"
        yield people
    finally:
        for user_id in user_ids:
            call("DELETE", f"/auth/v1/admin/users/{user_id}", SECRET_KEY)


def week(person, owner=None):
    owner = owner or person
    response = client.get(
        f"/api/profiles/{owner['profile_id']}/workout-plan?week_start={MONDAY.isoformat()}",
        headers=person["headers"],
    )
    assert response.status_code == 200, response.text
    return response.json()


def generate(person, reason="requested"):
    response = client.post(
        "/api/me/workout-plan/generate",
        json={"today": TODAY.isoformat(), "reason": reason},
        headers=person["headers"],
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_no_plan_yet(people):
    plan = week(people["a"])
    assert plan["active"] is None and plan["draft"] is None and plan["can_edit"]


def test_first_plan_is_made_and_active(people):
    result = generate(people["a"], reason="new_week")
    assert not result["generating"]
    plan = result["active"]
    assert plan and plan["made_by"] == "rules"
    remaining = 7 - TODAY.weekday()
    assert 1 <= len(plan["sessions"]) <= min(6, remaining)
    for session in plan["sessions"]:
        assert session["day"] >= TODAY.isoformat()
        assert {i["phase"] for i in session["items"]} == {
            "cardio",
            "mobility",
            "activation",
            "main",
            "cooldown",
        }
    assert plan["coverage"] and plan["coverage"][0]["sets"] > 0
    people["a"]["plan"] = plan


def test_new_week_again_changes_nothing(people):
    result = generate(people["a"], reason="new_week")
    assert result["active"]["id"] == people["a"]["plan"]["id"] and result["draft"] is None


def test_household_sees_the_plan_but_not_drafts_or_changes(people):
    a, b = people["a"], people["b"]
    seen = week(b, owner=a)
    assert seen["active"]["id"] == a["plan"]["id"] and seen["can_edit"] is False
    status, _ = call(
        "POST",
        "/rest/v1/rpc/save_workout_plan",
        PUBLISHABLE_KEY,
        b["token"],
        {
            "p_profile_id": a["profile_id"],
            "p_week_start": MONDAY.isoformat(),
            "p_status": "active",
            "p_plan": {},
        },
    )
    assert status in (401, 403)
    item_id = a["plan"]["sessions"][0]["items"][0]["id"]
    assert (
        client.get(
            f"/api/me/session-items/{item_id}/alternatives", headers=b["headers"]
        ).status_code
        == 404
    )


def test_swapping_an_exercise(people):
    a = people["a"]
    main = next(i for i in a["plan"]["sessions"][0]["items"] if i["phase"] == "main")
    options = client.get(
        f"/api/me/session-items/{main['id']}/alternatives", headers=a["headers"]
    ).json()
    assert options and all(o["id"] != main["exercise_id"] for o in options)
    assert all(set(o["primary_muscles"]) & set(main["primary_muscles"]) for o in options)
    refused = client.put(
        f"/api/me/session-items/{main['id']}/exercise",
        json={"exercise_id": "Barbell_Squat"},
        headers=a["headers"],
    )
    assert refused.status_code == 422  # not an offered swap (no barbell)
    swapped = client.put(
        f"/api/me/session-items/{main['id']}/exercise",
        json={"exercise_id": options[0]["id"]},
        headers=a["headers"],
    ).json()
    item = next(i for i in swapped["active"]["sessions"][0]["items"] if i["id"] == main["id"])
    assert item["exercise_id"] == options[0]["id"]


def test_new_plan_is_a_draft_that_can_be_applied_or_discarded(people):
    a = people["a"]
    first = generate(a)
    assert first["draft"] and first["active"]["id"] == a["plan"]["id"]
    discarded = client.delete(f"/api/me/workout-plans/{first['draft']['id']}", headers=a["headers"])
    assert discarded.json()["draft"] is None and discarded.json()["active"]["id"] == a["plan"]["id"]

    second = generate(a)
    applied = client.post(
        f"/api/me/workout-plans/{second['draft']['id']}/apply", headers=a["headers"]
    ).json()
    assert applied["active"]["id"] == second["draft"]["id"] and applied["draft"] is None
    _, old = call(
        "GET", f"/rest/v1/workout_plans?select=status&id=eq.{a['plan']['id']}", SECRET_KEY
    )
    assert old[0]["status"] == "superseded"


def test_signed_out_visitors_see_nothing():
    for table in (
        "workout_plans",
        "workout_sessions",
        "session_items",
        "exercise_logs",
        "session_completions",
    ):
        status, rows = call("GET", f"/rest/v1/{table}?select=id", PUBLISHABLE_KEY)
        assert status in (401, 403) or rows == []
