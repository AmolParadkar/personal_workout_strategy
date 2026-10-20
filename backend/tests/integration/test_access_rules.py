"""Checks the "view both, change your own" access rules against the real Supabase project.

Creates two temporary users, acts as each of them (and as a signed-out visitor)
through the same API the website uses, then deletes them.

Run after every migration:
    RUN_SUPABASE_TESTS=1 uv run pytest tests/integration -v
"""

import os
import secrets

import pytest

from tests.integration.supabase_client import CONFIGURED, PUBLISHABLE_KEY, SECRET_KEY, call

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_SUPABASE_TESTS") != "1" or not CONFIGURED,
    reason="Set RUN_SUPABASE_TESTS=1 (and fill in the .env files) to run against Supabase",
)

PERSON_TABLES = ["training_preferences", "diet_preferences", "display_settings"]
RETURN_ROWS = {"Prefer": "return=representation"}


@pytest.fixture(scope="module")
def users():
    """Two signed-in test users in the household; deleted afterwards."""
    user_ids: list[str] = []
    signed_in: dict[str, dict] = {}
    try:
        for name in ("a", "b"):
            password = secrets.token_urlsafe(16)
            email = f"access-test-{name}-{secrets.token_hex(3)}@example.com"
            status, user = call(
                "POST",
                "/auth/v1/admin/users",
                SECRET_KEY,
                body={
                    "email": email,
                    "password": password,
                    "email_confirm": True,
                    "user_metadata": {"display_name": f"Test {name.upper()}"},
                },
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

            status, rows = get(f"profiles?select=*&user_id=eq.{user['id']}", token)
            assert status == 200 and len(rows) == 1, rows
            signed_in[name] = {"token": token, "profile": rows[0]}
        yield signed_in
    finally:
        for user_id in user_ids:
            call("DELETE", f"/auth/v1/admin/users/{user_id}", SECRET_KEY)


def get(path, token=None):
    return call("GET", f"/rest/v1/{path}", PUBLISHABLE_KEY, token)


def patch(path, token, body):
    return call("PATCH", f"/rest/v1/{path}", PUBLISHABLE_KEY, token, body, RETURN_ROWS)


def test_new_users_get_profiles_in_one_household(users):
    a, b = users["a"]["profile"], users["b"]["profile"]
    assert a["display_name"] == "Test A"
    assert a["household_id"] == b["household_id"]


def test_each_user_can_read_both_profiles_and_settings(users):
    token = users["a"]["token"]
    ids = {users["a"]["profile"]["id"], users["b"]["profile"]["id"]}
    status, rows = get("profiles?select=id", token)
    assert status == 200 and ids <= {row["id"] for row in rows}
    for table in PERSON_TABLES:
        status, rows = get(f"{table}?select=profile_id", token)
        assert status == 200 and ids <= {row["profile_id"] for row in rows}, table


def test_opt_in_cards_are_off_by_default(users):
    status, rows = get(
        f"display_settings?select=*&profile_id=eq.{users['b']['profile']['id']}",
        users["b"]["token"],
    )
    assert status == 200
    assert rows[0]["show_weight"] is False
    assert rows[0]["show_calorie_intake"] is False
    assert rows[0]["show_calories_burned"] is False


def test_user_can_change_own_rows(users):
    token, profile_id = users["a"]["token"], users["a"]["profile"]["id"]
    status, rows = patch(f"profiles?id=eq.{profile_id}", token, {"height_cm": 175})
    assert status == 200 and rows[0]["height_cm"] == 175
    status, rows = patch(
        f"display_settings?profile_id=eq.{profile_id}", token, {"show_weight": True}
    )
    assert status == 200 and rows[0]["show_weight"] is True


def test_user_cannot_change_the_other_persons_rows(users):
    token, other_id = users["a"]["token"], users["b"]["profile"]["id"]
    status, rows = patch(f"profiles?id=eq.{other_id}", token, {"display_name": "changed"})
    assert status == 200 and rows == []
    for table in PERSON_TABLES:
        status, rows = patch(f"{table}?profile_id=eq.{other_id}", token, {})
        assert rows == [] or status in (400, 401, 403), table


def test_user_cannot_move_rows_to_another_person_or_household(users):
    token = users["a"]["token"]
    own_id, other_id = users["a"]["profile"]["id"], users["b"]["profile"]["id"]
    status, _ = patch(
        f"profiles?id=eq.{own_id}", token, {"household_id": "00000000-0000-0000-0000-000000000000"}
    )
    assert status in (401, 403)
    status, _ = patch(f"display_settings?profile_id=eq.{own_id}", token, {"profile_id": other_id})
    assert status in (401, 403)


def test_invalid_values_are_rejected(users):
    token, profile_id = users["a"]["token"], users["a"]["profile"]["id"]
    status, _ = patch(f"profiles?id=eq.{profile_id}", token, {"height_cm": 999})
    assert status == 400


def test_user_cannot_create_or_delete_profiles_or_households(users):
    token, profile = users["a"]["token"], users["a"]["profile"]
    status, _ = call(
        "POST",
        "/rest/v1/profiles",
        PUBLISHABLE_KEY,
        token,
        {
            "user_id": profile["user_id"],
            "household_id": profile["household_id"],
            "display_name": "x",
        },
    )
    assert status in (401, 403)
    status, _ = call("DELETE", f"/rest/v1/profiles?id=eq.{profile['id']}", PUBLISHABLE_KEY, token)
    assert status in (401, 403)
    status, _ = call("POST", "/rest/v1/households", PUBLISHABLE_KEY, token, {"name": "x"})
    assert status in (401, 403)


@pytest.mark.parametrize("table", ["households", "profiles", *PERSON_TABLES])
def test_signed_out_visitors_see_nothing(table):
    status, rows = get(f"{table}?select=*")
    assert status in (401, 403) or rows == []


def test_access_rule_helpers_are_not_exposed(users):
    status, _ = call(
        "POST", "/rest/v1/rpc/my_household_id", PUBLISHABLE_KEY, users["a"]["token"], {}
    )
    assert status in (400, 401, 403, 404)
