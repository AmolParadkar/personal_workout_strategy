"""75 Hard endpoints and access rules against the real Supabase project.

RUN_SUPABASE_TESTS=1 uv run pytest tests/integration -v
"""

import os
import secrets
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from api.main import app
from tests.integration.supabase_client import CONFIGURED, PUBLISHABLE_KEY, SECRET_KEY, call

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_SUPABASE_TESTS") != "1" or not CONFIGURED,
    reason="Set RUN_SUPABASE_TESTS=1 (and fill in the .env files) to run against Supabase",
)

client = TestClient(app)
TIMEZONE = "UTC"


@pytest.fixture(scope="module")
def people():
    """Two signed-in temporary users; deleted afterwards (their rows go with them)."""
    user_ids: list[str] = []
    people: dict[str, dict] = {}
    try:
        for name in ("a", "b"):
            password = secrets.token_urlsafe(16)
            email = f"hard-test-{name}-{secrets.token_hex(3)}@example.com"
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
        yield people
    finally:
        for user_id in user_ids:
            call("DELETE", f"/auth/v1/admin/users/{user_id}", SECRET_KEY)


def state(person, of=None):
    profile_id = (of or person)["profile_id"]
    response = client.get(
        f"/api/profiles/{profile_id}/seventy-five-hard", headers=person["headers"]
    )
    assert response.status_code == 200, response.json()
    return response.json()


def tick(person, day, item, checked=True):
    return client.put(
        "/api/me/seventy-five-hard/checks",
        json={"date": day, "item": item, "checked": checked},
        headers=person["headers"],
    )


def test_not_started_until_started(people):
    assert state(people["a"])["status"] == "not_started"


def test_start_on_the_day_you_say(people):
    a = people["a"]
    response = client.post(
        "/api/me/seventy-five-hard/start",
        json={"current_day": 12, "timezone": TIMEZONE},
        headers=a["headers"],
    )
    assert response.status_code == 200, response.json()
    assert response.json()["status"] == "active"
    assert response.json()["day"] == 12

    again = client.post(
        "/api/me/seventy-five-hard/start",
        json={"current_day": 1, "timezone": TIMEZONE},
        headers=a["headers"],
    )
    assert again.status_code == 409


def test_unknown_timezone_is_refused(people):
    response = client.post(
        "/api/me/seventy-five-hard/start",
        json={"current_day": 1, "timezone": "Mars/Base"},
        headers=people["b"]["headers"],
    )
    assert response.status_code == 422


def test_tick_and_untick_today(people):
    a = people["a"]
    today = state(a)["today"]["date"]
    response = tick(a, today, "water")
    assert response.status_code == 200
    assert {i["item"] for i in response.json()["today"]["items"] if i["checked"]} == {"water"}
    assert tick(a, today, "water").status_code == 200  # ticking twice is harmless
    response = tick(a, today, "water", checked=False)
    assert not any(i["checked"] for i in response.json()["today"]["items"])


def test_old_days_cannot_be_changed(people):
    a = people["a"]
    old = (date.fromisoformat(state(a)["today"]["date"]) - timedelta(days=5)).isoformat()
    assert tick(a, old, "water").status_code == 422


def test_other_person_sees_it_view_only(people):
    a, b = people["a"], people["b"]
    seen = state(b, of=a)
    assert seen["status"] == "active"
    assert seen["can_edit"] is False
    assert seen["today"]["editable"] is False
    profiles = client.get("/api/me/profiles", headers=b["headers"]).json()["profiles"]
    assert next(p for p in profiles if p["id"] == a["profile_id"])["doing_75_hard"] is True


def test_other_person_cannot_tick_or_stop_your_challenge(people):
    a, b = people["a"], people["b"]
    today = state(a)["today"]["date"]
    # Straight to the database with b's own token, bypassing the API.
    status, _ = call(
        "POST",
        "/rest/v1/challenge_checks",
        PUBLISHABLE_KEY,
        b["token"],
        {"profile_id": a["profile_id"], "date": today, "item": "diet"},
    )
    assert status in (401, 403)
    status, rows = call(
        "PATCH",
        f"/rest/v1/challenges?profile_id=eq.{a['profile_id']}",
        PUBLISHABLE_KEY,
        b["token"],
        {"stopped_at": "2026-01-01T00:00:00Z"},
        {"Prefer": "return=representation"},
    )
    assert rows == []
    assert state(a)["status"] == "active"


@pytest.mark.parametrize("table", ["challenges", "challenge_checks"])
def test_signed_out_visitors_see_nothing(table):
    status, rows = call("GET", f"/rest/v1/{table}?select=*", PUBLISHABLE_KEY)
    assert status in (401, 403) or rows == []


def test_stop(people):
    a = people["a"]
    response = client.post("/api/me/seventy-five-hard/stop", headers=a["headers"])
    assert response.status_code == 200
    assert response.json()["status"] == "not_started"
    assert client.post("/api/me/seventy-five-hard/stop", headers=a["headers"]).status_code == 409
