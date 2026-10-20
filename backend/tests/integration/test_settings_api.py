"""Settings / Profile endpoints against the real Supabase project.

Run after changes to settings or migrations:
    RUN_SUPABASE_TESTS=1 uv run pytest tests/integration -v
"""

import os
import secrets

import pytest
from fastapi.testclient import TestClient

from api.main import app
from tests.integration.supabase_client import CONFIGURED, PUBLISHABLE_KEY, SECRET_KEY, call

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_SUPABASE_TESTS") != "1" or not CONFIGURED,
    reason="Set RUN_SUPABASE_TESTS=1 (and fill in the .env files) to run against Supabase",
)

client = TestClient(app)


@pytest.fixture(scope="module")
def people():
    """Two signed-in temporary users; deleted afterwards."""
    user_ids: list[str] = []
    people: dict[str, dict] = {}
    try:
        for name in ("a", "b"):
            password = secrets.token_urlsafe(16)
            email = f"settings-test-{name}-{secrets.token_hex(3)}@example.com"
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
            headers = {"Authorization": f"Bearer {session['access_token']}"}
            profiles = client.get("/api/me/profiles", headers=headers).json()["profiles"]
            own = next(p for p in profiles if p["is_own"])
            people[name] = {"headers": headers, "profile_id": own["id"]}
        yield people
    finally:
        for user_id in user_ids:
            call("DELETE", f"/auth/v1/admin/users/{user_id}", SECRET_KEY)


def test_new_person_is_not_onboarded_and_can_edit_own_settings(people):
    a = people["a"]
    settings = client.get(f"/api/profiles/{a['profile_id']}/settings", headers=a["headers"]).json()
    assert settings["can_edit"] is True
    assert settings["profile"]["onboarded"] is False
    assert settings["display"] == {
        "show_weight": False,
        "show_calorie_intake": False,
        "show_calories_burned": False,
    }


def test_other_persons_settings_are_view_only(people):
    a, b = people["a"], people["b"]
    response = client.get(f"/api/profiles/{b['profile_id']}/settings", headers=a["headers"])
    assert response.status_code == 200
    assert response.json()["can_edit"] is False


def test_saving_a_section_changes_only_your_own_settings(people):
    a, b = people["a"], people["b"]
    response = client.patch(
        "/api/me/settings/display", json={"show_weight": True}, headers=a["headers"]
    )
    assert response.status_code == 200
    assert response.json()["display"]["show_weight"] is True
    other = client.get(f"/api/profiles/{b['profile_id']}/settings", headers=b["headers"]).json()
    assert other["display"]["show_weight"] is False


def test_invalid_values_are_rejected(people):
    headers = people["a"]["headers"]
    response = client.patch("/api/me/settings/profile", json={"height_cm": 999}, headers=headers)
    assert response.status_code == 422
    response = client.patch(
        "/api/me/settings/profile", json={"display_name": None}, headers=headers
    )
    assert response.status_code == 422


def test_onboarding_needs_required_fields_then_completes(people):
    a = people["a"]
    response = client.post("/api/me/onboarding/complete", headers=a["headers"])
    assert response.status_code == 422
    assert "height_cm" in response.json()["detail"]["missing"]

    steps = {
        "profile": {
            "display_name": "Tester",
            "date_of_birth": "1990-05-01",
            "sex": "other",
            "height_cm": 172.5,
            "goals": ["general_health", "endurance"],
            "goal_metric": "steps",
        },
        "training": {
            "available_days": ["sat", "mon"],
            "minutes_per_session": 45,
            "location": "home",
        },
        "diet": {"diet_type": "vegetarian", "meals_per_day": 3, "allergies": ["peanuts", " "]},
    }
    for section, values in steps.items():
        response = client.patch(f"/api/me/settings/{section}", json=values, headers=a["headers"])
        assert response.status_code == 200, response.json()

    saved = response.json()
    assert saved["training"]["available_days"] == ["mon", "sat"]
    assert saved["diet"]["allergies"] == ["peanuts"]

    response = client.post("/api/me/onboarding/complete", headers=a["headers"])
    assert response.status_code == 200
    assert response.json()["profile"]["onboarded"] is True
    profiles = client.get("/api/me/profiles", headers=a["headers"]).json()["profiles"]
    assert next(p for p in profiles if p["is_own"])["onboarded"] is True


def test_settings_need_sign_in():
    assert client.get("/api/me/profiles").status_code == 401
    assert client.patch("/api/me/settings/display", json={}).status_code == 401
