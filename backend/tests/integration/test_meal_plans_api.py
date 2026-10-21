"""Meal plans against the real Supabase project: the imported foods, making a plan
(rules only, so Groq's limits don't matter), a weigh-in first, swaps, eating out
with a preview, the household grocery list and the access rules.

RUN_SUPABASE_TESTS=1 uv run pytest tests/integration -v
"""

import os
import secrets
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api.main import app
from core.nutrition import generate as generator
from core.nutrition import plans as plan_service
from tests.integration.supabase_client import CONFIGURED, PUBLISHABLE_KEY, SECRET_KEY, call

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_SUPABASE_TESTS") != "1" or not CONFIGURED,
    reason="Set RUN_SUPABASE_TESTS=1 (and fill in the .env files) to run against Supabase",
)

client = TestClient(app)
TODAY = datetime.now(UTC).date()
MONDAY = TODAY - timedelta(days=TODAY.weekday())


@pytest.fixture(autouse=True)
def rules_only_plans(monkeypatch):
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
            email = f"meal-test-{name}-{secrets.token_hex(3)}@example.com"
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
            people[name] = {
                "headers": headers,
                "token": session["access_token"],
                "profile_id": own["id"],
            }
        a = people["a"]
        profile = {
            "date_of_birth": "1990-03-01",
            "sex": "female",
            "height_cm": 165,
            "goals": ["lose_fat", "get_stronger"],
        }
        diet = {
            "diet_type": "vegetarian",
            "cuisines": ["Indian"],
            "allergies": ["Capsicum"],
            "meals_per_day": 3,
            "cooking_minutes": 30,
        }
        for section, body in (("profile", profile), ("diet", diet)):
            response = client.patch(f"/api/me/settings/{section}", json=body, headers=a["headers"])
            assert response.status_code == 200, response.text
        yield people
    finally:
        for user_id in user_ids:
            call("DELETE", f"/auth/v1/admin/users/{user_id}", SECRET_KEY)


def make_plan(person, reason="new_week"):
    response = client.post(
        "/api/me/meal-plan/generate",
        json={"today": TODAY.isoformat(), "reason": reason},
        headers=person["headers"],
    )
    assert response.status_code == 200, response.text
    return response.json()


def week_of(person, owner=None):
    owner = owner or person
    response = client.get(
        f"/api/profiles/{owner['profile_id']}/meal-plan?week_start={MONDAY.isoformat()}",
        headers=person["headers"],
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_foods_are_imported_and_readable_when_signed_in(people):
    status, rows = call(
        "GET",
        "/rest/v1/foods?select=id,role&role=eq.main&limit=5",
        PUBLISHABLE_KEY,
        people["a"]["token"],
    )
    assert status == 200 and len(rows) == 5
    status, rows = call("GET", "/rest/v1/foods?select=id&limit=1", PUBLISHABLE_KEY)
    assert status in (401, 403) or rows == []


def test_no_weigh_in_means_the_page_asks_for_one(people):
    week = make_plan(people["a"])
    assert week["missing"] == ["weight"] and week["active"] is None


def test_plan_after_a_weigh_in(people):
    a = people["a"]
    response = client.post(
        "/api/me/weight", json={"kg": 64.5, "date": TODAY.isoformat()}, headers=a["headers"]
    )
    assert response.status_code == 200, response.text
    week = make_plan(a)
    plan = week["active"]
    assert plan and week["missing"] == []
    a["plan"] = plan
    days = plan["days"]
    assert (
        days[0]["day"] == TODAY.isoformat()
        and days[-1]["day"] == (MONDAY + timedelta(days=6)).isoformat()
    )
    first = days[0]
    assert [m["slot"] for m in first["meals"]] == ["breakfast", "lunch", "dinner"]
    assert first["targets"]["kcal"] >= 1200 and first["targets"]["reasons"]["protein_g"]
    assert abs(first["totals"]["kcal"] - first["targets"]["kcal"]) / first["targets"]["kcal"] < 0.3
    names = " ".join(i["name"].lower() for d in days for m in d["meals"] for i in m["items"])
    assert "chicken" not in names and "capsicum" not in names
    # Asking again for a new week changes nothing.
    assert make_plan(a)["active"]["id"] == plan["id"]


def test_the_other_person_sees_but_cannot_change_it(people):
    a, b = people["a"], people["b"]
    seen = week_of(b, owner=a)
    # Not in the same household: nothing to see.
    assert seen["active"] is None or seen["can_edit"] is False
    meal_id = a["plan"]["days"][0]["meals"][1]["id"]
    refused = client.get(
        f"/api/me/planned-meals/{meal_id}/alternatives?today={TODAY.isoformat()}",
        headers=b["headers"],
    )
    assert refused.status_code == 404
    status, _ = call(
        "PATCH",
        f"/rest/v1/planned_meals?id=eq.{meal_id}",
        PUBLISHABLE_KEY,
        b["token"],
        {"name": "Hacked"},
    )
    assert status in (200, 204, 401, 403)
    assert week_of(a)["active"]["days"][0]["meals"][1]["name"] != "Hacked"


def test_swapping_a_dish(people):
    a = people["a"]
    meal = a["plan"]["days"][0]["meals"][1]
    options = client.get(
        f"/api/me/planned-meals/{meal['id']}/alternatives?today={TODAY.isoformat()}",
        headers=a["headers"],
    ).json()
    assert options and all(o["diet"] == "vegetarian" for o in options)
    choice = options[0]
    week = client.put(
        f"/api/me/planned-meals/{meal['id']}/food?today={TODAY.isoformat()}",
        json={"food_id": choice["id"]},
        headers=a["headers"],
    ).json()
    swapped = week["active"]["days"][0]["meals"][1]
    assert swapped["items"][0]["food_id"] == choice["id"]
    bad = client.put(
        f"/api/me/planned-meals/{meal['id']}/food?today={TODAY.isoformat()}",
        json={"food_id": "usda-171477"},
        headers=a["headers"],
    )
    assert bad.status_code == 422


def test_eating_out_previews_then_applies(people):
    a = people["a"]
    plan = week_of(a)["active"]
    dinner = plan["days"][0]["meals"][2]
    week = client.post(
        "/api/me/meal-plan/eating-out",
        json={"today": TODAY.isoformat(), "meal_ids": [dinner["id"]]},
        headers=a["headers"],
    ).json()
    draft = week["draft"]
    assert draft and draft["change_note"].startswith("Eating out")
    assert draft["days"][0]["meals"][2]["kind"] == "eating_out"
    applied = client.post(f"/api/me/meal-plans/{draft['id']}/apply", headers=a["headers"]).json()
    assert applied["draft"] is None
    assert applied["active"]["days"][0]["meals"][2]["name"] == "Eating out"
    eaten_out = applied["active"]["days"][0]["meals"][2]["id"]
    again = client.post(
        "/api/me/meal-plan/eating-out",
        json={"today": TODAY.isoformat(), "meal_ids": [eaten_out]},
        headers=a["headers"],
    )
    assert again.status_code == 422


def test_a_new_plan_is_a_preview_that_can_be_discarded(people):
    a = people["a"]
    week = make_plan(a, reason="requested")
    assert week["draft"] and week["active"]
    after = client.delete(f"/api/me/meal-plans/{week['draft']['id']}", headers=a["headers"]).json()
    assert after["draft"] is None and after["active"]["id"] == week["active"]["id"]


def test_grocery_list(people):
    a = people["a"]
    result = client.get(
        f"/api/grocery-list?week_start={MONDAY.isoformat()}&from_day={TODAY.isoformat()}",
        headers=a["headers"],
    ).json()
    assert result["groups"] and any(p["has_plan"] for p in result["people"])
    items = [i for g in result["groups"] for i in g["items"]]
    assert all(i["name"] and i["for_people"] for i in items)


def test_only_own_plans_are_saved(people):
    b = people["b"]
    status, _ = call(
        "POST",
        "/rest/v1/rpc/save_meal_plan",
        PUBLISHABLE_KEY,
        b["token"],
        {
            "p_profile_id": people["a"]["profile_id"],
            "p_week_start": MONDAY.isoformat(),
            "p_status": "active",
            "p_plan": {"days": []},
        },
    )
    assert status in (401, 403)
