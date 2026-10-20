import pytest
from fastapi.testclient import TestClient

from api.deps import get_supabase
from api.main import app
from core.supabase import NotSignedInError

OWN_USER_ID = "user-amol"
VALID_TOKEN = "valid-token"

ROWS = [
    {
        "id": "profile-spouse",
        "user_id": "user-spouse",
        "display_name": "Spouse",
        "onboarded_at": None,
    },
    {
        "id": "profile-amol",
        "user_id": OWN_USER_ID,
        "display_name": "Amol",
        "onboarded_at": "2026-10-20T12:00:00Z",
        "challenges": [{"id": "challenge-1"}],
    },
]


class FakeSupabase:
    """Stands in for Supabase: accepts one token and returns fixed profiles."""

    async def get_user_id(self, access_token: str) -> str:
        if access_token != VALID_TOKEN:
            raise NotSignedInError
        return OWN_USER_ID

    async def get_household_profiles(self, access_token: str) -> list[dict]:
        return ROWS


async def fake_supabase():
    yield FakeSupabase()


client = TestClient(app)


@pytest.fixture(autouse=True)
def use_fake_supabase():
    # Only for these tests: integration tests must reach the real Supabase.
    app.dependency_overrides[get_supabase] = fake_supabase
    yield
    app.dependency_overrides.clear()


def test_returns_household_profiles_with_own_first():
    response = client.get("/api/me/profiles", headers={"Authorization": f"Bearer {VALID_TOKEN}"})

    assert response.status_code == 200
    assert response.json() == {
        "profiles": [
            {
                "id": "profile-amol",
                "display_name": "Amol",
                "is_own": True,
                "onboarded": True,
                "doing_75_hard": True,
            },
            {
                "id": "profile-spouse",
                "display_name": "Spouse",
                "is_own": False,
                "onboarded": False,
                "doing_75_hard": False,
            },
        ]
    }


def test_rejects_missing_token():
    assert client.get("/api/me/profiles").status_code == 401


def test_rejects_invalid_token():
    response = client.get("/api/me/profiles", headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401


def test_allows_the_website_origin():
    response = client.options(
        "/api/me/profiles",
        headers={
            "Origin": "http://localhost:8081",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )
    assert response.headers.get("access-control-allow-origin") == "http://localhost:8081"
