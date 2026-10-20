"""Health data intake against the real Supabase project.

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
    """Two signed-in temporary users; deleted afterwards (their data goes with them)."""
    user_ids: list[str] = []
    people: dict[str, dict] = {}
    try:
        for name in ("a", "b"):
            password = secrets.token_urlsafe(16)
            email = f"health-test-{name}-{secrets.token_hex(3)}@example.com"
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


def ingest(token, samples):
    return client.post(
        "/api/ingest/health",
        json={"samples": samples},
        headers={"Authorization": f"Bearer {token}"},
    )


def samples_of(person, metric):
    status, rows = call(
        "GET",
        f"/rest/v1/health_samples?select=value,recorded_on,recorded_at,source"
        f"&profile_id=eq.{person['profile_id']}&metric=eq.{metric}",
        PUBLISHABLE_KEY,
        person["token"],
    )
    assert status == 200
    return rows


def today(person):
    """Today's date as the 75 Hard calculation sees it (UTC challenges in these tests)."""
    from datetime import UTC, datetime

    return datetime.now(UTC).date().isoformat()


# --- Apple Health connection -------------------------------------------------


def test_not_connected_until_a_token_is_created(people):
    response = client.get("/api/me/health-connection", headers=people["a"]["headers"])
    assert response.json() == {
        "connected": False,
        "created_at": None,
        "last_used_at": None,
        "latest_data_on": None,
    }


def test_shortcut_data_is_saved_with_the_connection_token(people):
    a = people["a"]
    created = client.post("/api/me/health-connection", headers=a["headers"]).json()
    a["ingest_token"] = created["token"]
    assert created["token"].startswith("wst_")

    response = ingest(
        created["token"],
        [
            {"metric": "steps", "date": "2026-10-19", "value": 8421},
            {"metric": "sleep_in_bed_minutes", "date": "2026-10-20", "value": 455},
            {"metric": "bedtime", "date": "2026-10-20", "at": "2026-10-19T23:40:00+05:30"},
        ],
    )
    assert response.status_code == 200, response.json()
    assert response.json() == {"saved": 3, "skipped": []}
    assert samples_of(a, "steps")[0]["value"] == 8421

    connection = client.get("/api/me/health-connection", headers=a["headers"]).json()
    assert connection["connected"] is True
    assert connection["last_used_at"] is not None
    assert connection["latest_data_on"] == "2026-10-20"


def test_sending_the_same_day_again_replaces_it(people):
    a = people["a"]
    ingest(a["ingest_token"], [{"metric": "steps", "date": "2026-10-19", "value": 9000}])
    rows = samples_of(a, "steps")
    assert len(rows) == 1
    assert rows[0]["value"] == 9000


def test_bad_tokens_are_refused_and_bad_values_skipped(people):
    assert (
        ingest("wst_made_up", [{"metric": "steps", "date": "2026-10-19", "value": 1}]).status_code
        == 401
    )
    response = client.post("/api/ingest/health", json={"samples": []})
    assert response.status_code in (401, 422)
    mixed = ingest(
        people["a"]["ingest_token"],
        [
            {"metric": "weight_kg", "date": "2026-10-19", "value": 0},
            {"metric": "walking_running_km", "date": "2026-10-19", "value": "6.4"},
        ],
    )
    assert mixed.status_code == 200
    assert mixed.json()["saved"] == 1
    assert mixed.json()["skipped"][0]["metric"] == "weight_kg"


def test_a_new_token_cancels_the_old_one(people):
    a = people["a"]
    old = a["ingest_token"]
    a["ingest_token"] = client.post("/api/me/health-connection", headers=a["headers"]).json()[
        "token"
    ]
    sample = [{"metric": "steps", "date": "2026-10-19", "value": 1}]
    assert ingest(old, sample).status_code == 401
    assert ingest(a["ingest_token"], sample).status_code == 200


def test_tokens_are_private_even_in_the_household(people):
    a, b = people["a"], people["b"]
    status, rows = call(
        "GET",
        f"/rest/v1/ingest_tokens?select=id&profile_id=eq.{a['profile_id']}",
        PUBLISHABLE_KEY,
        b["token"],
    )
    assert rows == []
    status, _ = call("GET", "/rest/v1/ingest_tokens?select=token_hash", PUBLISHABLE_KEY, a["token"])
    assert status in (401, 403)  # the hash column is never readable


def test_other_person_can_read_but_not_add_measurements(people):
    a, b = people["a"], people["b"]
    assert len(samples_of({"profile_id": a["profile_id"], "token": b["token"]}, "steps")) == 1
    status, _ = call(
        "POST",
        "/rest/v1/health_samples",
        PUBLISHABLE_KEY,
        b["token"],
        {"profile_id": a["profile_id"], "metric": "steps", "recorded_on": "2026-10-18", "value": 5},
    )
    assert status in (401, 403)


def test_removing_the_connection(people):
    a = people["a"]
    response = client.delete("/api/me/health-connection", headers=a["headers"])
    assert response.json()["connected"] is False
    sample = [{"metric": "steps", "date": "2026-10-19", "value": 1}]
    assert ingest(a["ingest_token"], sample).status_code == 401


# --- Water ---------------------------------------------------------------------


def test_water_add_undo_and_view_only(people):
    a, b = people["a"], people["b"]
    day = today(a)
    response = client.post("/api/me/water", json={"ml": 250, "date": day}, headers=a["headers"])
    assert response.status_code == 200, response.json()
    response = client.post("/api/me/water", json={"ml": 500, "date": day}, headers=a["headers"])
    water = response.json()
    assert water["total_ml"] == 750
    assert water["target_ml"] == 3000
    assert water["can_edit"] is True

    last = water["logs"][-1]["id"]
    water = client.delete(f"/api/me/water/{last}?day={day}", headers=a["headers"]).json()
    assert water["total_ml"] == 250

    seen = client.get(f"/api/profiles/{a['profile_id']}/water?day={day}", headers=b["headers"])
    assert seen.json()["total_ml"] == 250
    assert seen.json()["can_edit"] is False

    # b can't undo a's glass
    first = water["logs"][0]["id"]
    after = client.delete(f"/api/me/water/{first}?day={day}", headers=b["headers"]).json()
    assert after["total_ml"] == 0  # b's own (empty) day
    still = client.get(f"/api/profiles/{a['profile_id']}/water?day={day}", headers=a["headers"])
    assert still.json()["total_ml"] == 250


def test_water_dates_far_from_today_are_refused(people):
    response = client.post(
        "/api/me/water", json={"ml": 250, "date": "2020-01-01"}, headers=people["a"]["headers"]
    )
    assert response.status_code == 422


def test_water_target_is_set_in_settings(people):
    a = people["a"]
    client.patch("/api/me/settings/profile", json={"water_target_ml": 3500}, headers=a["headers"])
    water = client.get(
        f"/api/profiles/{a['profile_id']}/water?day={today(a)}", headers=a["headers"]
    ).json()
    assert water["target_ml"] == 3500


def test_a_gallon_ticks_the_75_hard_water_item(people):
    b = people["b"]
    day = today(b)
    client.post(
        "/api/me/seventy-five-hard/start",
        json={"current_day": 3, "timezone": "UTC"},
        headers=b["headers"],
    )
    for _ in range(3):
        client.post("/api/me/water", json={"ml": 1000, "date": day}, headers=b["headers"])
    hard = client.get(f"/api/profiles/{b['profile_id']}/seventy-five-hard", headers=b["headers"])
    water_item = next(i for i in hard.json()["today"]["items"] if i["item"] == "water")
    assert water_item["checked"] is False  # 3 L isn't a gallon yet

    client.post("/api/me/water", json={"ml": 800, "date": day}, headers=b["headers"])
    hard = client.get(f"/api/profiles/{b['profile_id']}/seventy-five-hard", headers=b["headers"])
    water_item = next(i for i in hard.json()["today"]["items"] if i["item"] == "water")
    assert water_item["checked"] is True


# --- Body weight ---------------------------------------------------------------


def test_weight_log_correct_and_view(people):
    a, b = people["a"], people["b"]
    url = f"/api/profiles/{a['profile_id']}/weight"
    assert client.get(url, headers=a["headers"]).json() == {"latest": None, "can_edit": True}

    day = today(a)
    client.post("/api/me/weight", json={"kg": 82.4, "date": day}, headers=a["headers"])
    summary = client.post("/api/me/weight", json={"kg": 82.1, "date": day}, headers=a["headers"])
    assert summary.json()["latest"] == {"kg": 82.1, "date": day, "source": "manual"}
    assert len(samples_of(a, "weight_kg")) == 1  # corrected, not duplicated

    seen = client.get(url, headers=b["headers"]).json()
    assert seen["latest"]["kg"] == 82.1
    assert seen["can_edit"] is False

    bad = client.post("/api/me/weight", json={"kg": 900, "date": day}, headers=a["headers"])
    assert bad.status_code == 422


@pytest.mark.parametrize("table", ["health_samples", "ingest_tokens", "water_logs"])
def test_signed_out_visitors_see_nothing(table):
    status, rows = call("GET", f"/rest/v1/{table}?select=id", PUBLISHABLE_KEY)
    assert status in (401, 403) or rows == []
