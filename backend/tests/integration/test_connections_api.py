"""Direct connections against the real Supabase project (no real health services:
the service side is faked, the database and its access rules are real).

RUN_SUPABASE_TESTS=1 uv run pytest tests/integration -v
"""

import os
import secrets
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from api.main import app
from api.routes import connections as connection_routes
from core.config import get_settings
from core.connectors import CONNECTORS
from core.connectors import keys as connector_keys
from core.connectors.base import Tokens
from tests.integration.supabase_client import CONFIGURED, PUBLISHABLE_KEY, SECRET_KEY, call

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_SUPABASE_TESTS") != "1" or not CONFIGURED,
    reason="Set RUN_SUPABASE_TESTS=1 (and fill in the .env files) to run against Supabase",
)

client = TestClient(app)
KEY = Fernet.generate_key().decode()
SITE = "http://localhost:8081"


@pytest.fixture(scope="module")
def people():
    """Two signed-in temporary users in one household; deleted afterwards."""
    user_ids: list[str] = []
    people: dict[str, dict] = {}
    try:
        for name in ("a", "b"):
            password = secrets.token_urlsafe(16)
            email = f"connect-test-{name}-{secrets.token_hex(3)}@example.com"
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


@pytest.fixture
def configured(monkeypatch):
    """The API as if the Oura developer app were set up."""
    settings = get_settings().model_copy(
        update={
            "connector_encryption_key": KEY,
            "oura_client_id": "test-client",
            "oura_client_secret": "test-secret",
            "cors_origins": SITE,
        }
    )
    monkeypatch.setattr(connection_routes, "get_settings", lambda: settings)
    return settings


class FakeOura:
    """Stands in for Oura's servers."""

    service = "oura"
    label = "Oura"

    async def exchange_code(self, http, client, code, redirect_uri):
        assert code == "good-code"
        return Tokens("access-1", "refresh-1", datetime.now(UTC) + timedelta(days=1), "oura-user")

    async def refresh(self, http, client, tokens):
        return Tokens("access-2", "refresh-2", datetime.now(UTC) + timedelta(days=1))

    async def fetch(self, http, tokens, start, end):
        return [
            {"metric": "steps", "date": end.isoformat(), "value": 7000},
            {"metric": "readiness_score", "date": end.isoformat(), "value": 81},
        ]

    async def revoke(self, http, client, tokens):
        return None


@pytest.fixture
def fake_oura(monkeypatch):
    monkeypatch.setitem(CONNECTORS, "oura", FakeOura())


def today() -> str:
    return datetime.now(UTC).date().isoformat()


def status_of(person, service="oura"):
    response = client.get(
        f"/api/profiles/{person['profile_id']}/connections", headers=person["headers"]
    )
    assert response.status_code == 200, response.text
    return next(s for s in response.json()["services"] if s["service"] == service)


def test_nothing_connected_and_unset_services_unavailable(people):
    a = people["a"]
    services = client.get(
        f"/api/profiles/{a['profile_id']}/connections", headers=a["headers"]
    ).json()
    assert [s["service"] for s in services["services"]] == ["withings", "oura", "whoop", "polar"]
    assert not any(s["connected"] for s in services["services"])
    assert services["can_edit"] is True


def test_start_needs_the_service_set_up_and_our_own_return_address(people, configured):
    a = people["a"]
    unset = client.post(
        "/api/me/connections/whoop/start",
        json={"redirect_uri": f"{SITE}/connect/whoop"},
        headers=a["headers"],
    )
    assert unset.status_code == 409
    evil = client.post(
        "/api/me/connections/oura/start",
        json={"redirect_uri": "https://evil.example/connect/oura"},
        headers=a["headers"],
    )
    assert evil.status_code == 422
    ok = client.post(
        "/api/me/connections/oura/start",
        json={"redirect_uri": f"{SITE}/connect/oura"},
        headers=a["headers"],
    )
    assert ok.status_code == 200
    assert ok.json()["url"].startswith("https://cloud.ouraring.com/oauth/authorize?")


def test_someone_elses_sign_in_state_is_refused(people, configured, fake_oura):
    a, b = people["a"], people["b"]
    state_for_a = connector_keys.sign_state(KEY, a["profile_id"], "oura")
    response = client.post(
        "/api/me/connections/oura/complete",
        json={
            "code": "good-code",
            "state": state_for_a,
            "redirect_uri": f"{SITE}/connect/oura",
            "today": today(),
        },
        headers=b["headers"],
    )
    assert response.status_code == 400
    assert status_of(b)["connected"] is False


def test_connecting_saves_encrypted_keys_and_fetches_data(people, configured, fake_oura):
    a = people["a"]
    state = connector_keys.sign_state(KEY, a["profile_id"], "oura")
    response = client.post(
        "/api/me/connections/oura/complete",
        json={
            "code": "good-code",
            "state": state,
            "redirect_uri": f"{SITE}/connect/oura",
            "today": today(),
        },
        headers=a["headers"],
    )
    assert response.status_code == 200, response.text
    assert response.json()["saved"] == 2
    status = status_of(a)
    assert status["connected"] and status["last_synced_at"] and not status["needs_reconnect"]

    status_code, rows = call(
        "GET",
        f"/rest/v1/health_samples?select=metric,value,source&profile_id=eq.{a['profile_id']}&source=eq.oura",
        PUBLISHABLE_KEY,
        a["token"],
    )
    assert status_code == 200
    assert {(r["metric"], float(r["value"])) for r in rows} == {
        ("steps", 7000),
        ("readiness_score", 81),
    }

    # Keys are stored encrypted, and only for the owner.
    status_code, mine = call(
        "POST", "/rest/v1/rpc/my_service_connection_keys", PUBLISHABLE_KEY, a["token"], {}
    )
    assert status_code == 200 and len(mine) == 1
    assert "access-1" not in str(mine)
    assert connector_keys.decrypt(KEY, mine[0]["access_token_enc"]) == "access-1"


def test_key_columns_are_never_readable(people):
    a = people["a"]
    status, _ = call(
        "GET", "/rest/v1/service_connections?select=access_token_enc", PUBLISHABLE_KEY, a["token"]
    )
    assert status in (401, 403)


def test_household_sees_status_but_not_keys_and_cant_change_it(people):
    a, b = people["a"], people["b"]
    seen = client.get(f"/api/profiles/{a['profile_id']}/connections", headers=b["headers"]).json()
    assert seen["can_edit"] is False
    assert next(s for s in seen["services"] if s["service"] == "oura")["connected"] is True
    status, theirs = call(
        "POST", "/rest/v1/rpc/my_service_connection_keys", PUBLISHABLE_KEY, b["token"], {}
    )
    assert status == 200 and theirs == []
    # B can't delete or edit A's connection.
    call(
        "DELETE",
        f"/rest/v1/service_connections?profile_id=eq.{a['profile_id']}",
        PUBLISHABLE_KEY,
        b["token"],
    )
    call(
        "PATCH",
        f"/rest/v1/service_connections?profile_id=eq.{a['profile_id']}",
        PUBLISHABLE_KEY,
        b["token"],
        {"needs_reconnect": True},
    )
    assert status_of(a)["connected"] is True and status_of(a)["needs_reconnect"] is False


def test_samples_only_for_services_you_have_connected(people):
    b = people["b"]
    status, _ = call(
        "POST",
        "/rest/v1/rpc/save_service_samples",
        PUBLISHABLE_KEY,
        b["token"],
        {"p_service": "oura", "p_samples": [{"metric": "steps", "date": "2026-10-19", "value": 1}]},
    )
    assert status in (401, 403)
    status, _ = call(
        "POST",
        "/rest/v1/rpc/save_service_samples",
        PUBLISHABLE_KEY,
        None,
        {"p_service": "oura", "p_samples": []},
    )
    assert status in (401, 403)


def test_sync_waits_3_hours_unless_forced_and_refreshes_keys(people, configured, fake_oura):
    a = people["a"]
    body = {"today": today()}
    first = client.post("/api/me/connections/sync", json=body, headers=a["headers"]).json()
    assert first["results"] == [{"service": "oura", "saved": 0, "skipped": True, "error": None}]
    forced = client.post(
        "/api/me/connections/sync", json={**body, "force": True}, headers=a["headers"]
    )
    assert forced.status_code == 200
    assert forced.json()["results"][0]["saved"] == 2


def test_disconnecting_deletes_the_keys(people, configured, fake_oura):
    a = people["a"]
    response = client.delete("/api/me/connections/oura", headers=a["headers"])
    assert response.status_code == 200
    assert (
        next(s for s in response.json()["services"] if s["service"] == "oura")["connected"] is False
    )
    status, mine = call(
        "POST", "/rest/v1/rpc/my_service_connection_keys", PUBLISHABLE_KEY, a["token"], {}
    )
    assert mine == []
    # Data already fetched stays (it's the person's history).
    status, rows = call(
        "GET",
        f"/rest/v1/health_samples?select=id&profile_id=eq.{a['profile_id']}&source=eq.oura",
        PUBLISHABLE_KEY,
        a["token"],
    )
    assert len(rows) == 2


def test_new_apps_and_devices_can_be_chosen(people):
    a = people["a"]
    response = client.patch(
        "/api/me/settings/profile",
        json={"data_sources": ["polar", "dexcom", "amazfit"]},
        headers=a["headers"],
    )
    assert response.status_code == 200, response.text
    assert set(response.json()["profile"]["data_sources"]) == {"polar", "dexcom", "amazfit"}


def test_signed_out_visitors_see_nothing():
    status, rows = call("GET", "/rest/v1/service_connections?select=id", PUBLISHABLE_KEY)
    assert status in (401, 403) or rows == []
    status, _ = call("POST", "/rest/v1/rpc/my_service_connection_keys", PUBLISHABLE_KEY, None, {})
    assert status in (401, 403) or _ == []
