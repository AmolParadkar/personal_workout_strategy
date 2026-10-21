"""Exercise library against the real Supabase project (no LLM or YouTube calls:
only the library, its access rules and the queueing of guide/video jobs).

RUN_SUPABASE_TESTS=1 uv run pytest tests/integration -v
Stop the Mac worker first, or it may pick up the queued jobs mid-test.
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
# An exercise unlikely to have a guide yet; restored after the tests.
EXERCISE = "Zottman_Preacher_Curl"


@pytest.fixture(scope="module")
def person():
    password = secrets.token_urlsafe(16)
    email = f"exercise-test-{secrets.token_hex(3)}@example.com"
    status, user = call(
        "POST",
        "/auth/v1/admin/users",
        SECRET_KEY,
        body={"email": email, "password": password, "email_confirm": True},
    )
    assert status == 200, user
    _, before = call("GET", f"/rest/v1/exercises?select=*&id=eq.{EXERCISE}", SECRET_KEY)
    try:
        status, session = call(
            "POST",
            "/auth/v1/token?grant_type=password",
            PUBLISHABLE_KEY,
            body={"email": email, "password": password},
        )
        assert status == 200, session
        token = session["access_token"]
        yield {"headers": {"Authorization": f"Bearer {token}"}, "token": token}
    finally:
        call("DELETE", f"/auth/v1/admin/users/{user['id']}", SECRET_KEY)  # their jobs go too
        guide_and_video = {
            k: before[0][k]
            for k in ("about", "form_cues", "precautions", "guide_written_at", "video_checked_at")
        }
        call("PATCH", f"/rest/v1/exercises?id=eq.{EXERCISE}", SECRET_KEY, body=guide_and_video)


def test_library_is_imported_and_searchable(person):
    everything = client.get("/api/exercises", headers=person["headers"]).json()
    assert len(everything["items"]) == 30 and everything["has_more"]
    squats = client.get("/api/exercises?search=squat", headers=person["headers"]).json()
    assert squats["items"] and all("squat" in e["name"].lower() for e in squats["items"])
    assert squats["items"][0]["image"].startswith("https://cdn.jsdelivr.net/")
    chest = client.get(
        "/api/exercises?muscle=chest&equipment=dumbbell", headers=person["headers"]
    ).json()
    assert all(
        "chest" in e["primary_muscles"] and e["equipment"] == "dumbbell" for e in chest["items"]
    )
    assert client.get("/api/exercises?muscle=ears", headers=person["headers"]).status_code == 422


def test_one_exercise_in_detail(person):
    detail = client.get(f"/api/exercises/{EXERCISE}", headers=person["headers"]).json()
    assert detail["name"] and len(detail["images"]) == 2 and detail["instructions"]
    missing = client.get("/api/exercises/No_Such_Exercise", headers=person["headers"])
    assert missing.status_code == 404


def test_prepare_queues_the_guide_and_video_once(person):
    # Start from "nothing prepared yet".
    call(
        "PATCH",
        f"/rest/v1/exercises?id=eq.{EXERCISE}",
        SECRET_KEY,
        body={"guide_written_at": None, "video_checked_at": None},
    )
    first = client.post(f"/api/exercises/{EXERCISE}/prepare", headers=person["headers"]).json()
    assert first["guide_status"] == first["video_status"] == "preparing"
    client.post(f"/api/exercises/{EXERCISE}/prepare", headers=person["headers"])
    status, jobs = call(
        "GET",
        f"/rest/v1/jobs?select=type&payload->>exercise_id=eq.{EXERCISE}&status=eq.pending",
        PUBLISHABLE_KEY,
        person["token"],
    )
    assert sorted(j["type"] for j in jobs) == ["find_exercise_video", "write_exercise_guide"]


def test_library_is_read_only_from_the_website(person):
    call(
        "PATCH",
        f"/rest/v1/exercises?id=eq.{EXERCISE}",
        PUBLISHABLE_KEY,
        person["token"],
        {"about": "Hacked"},
    )
    _, rows = call("GET", f"/rest/v1/exercises?select=about&id=eq.{EXERCISE}", SECRET_KEY)
    assert rows[0]["about"] != "Hacked"
    status, _ = call(
        "POST",
        "/rest/v1/exercises",
        PUBLISHABLE_KEY,
        person["token"],
        {"id": "Fake", "name": "Fake"},
    )
    assert status in (401, 403)


def test_signed_out_visitors_see_nothing():
    status, rows = call("GET", "/rest/v1/exercises?select=id&limit=1", PUBLISHABLE_KEY)
    assert status in (401, 403) or rows == []
