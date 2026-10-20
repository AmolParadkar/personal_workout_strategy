"""Job queue and worker against the real Supabase project.

RUN_SUPABASE_TESTS=1 uv run pytest tests/integration -v
The worker part uses the backend-api secret key in place of mac-worker.
"""

import asyncio
import os
import secrets
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api.main import app
from tests.integration.supabase_client import CONFIGURED, PUBLISHABLE_KEY, SECRET_KEY, URL, call
from worker import main as worker
from worker.config import WorkerSettings

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_SUPABASE_TESTS") != "1" or not CONFIGURED,
    reason="Set RUN_SUPABASE_TESTS=1 (and fill in the .env files) to run against Supabase",
)

client = TestClient(app)
WORKER_ID = f"test-worker-{secrets.token_hex(3)}"


@pytest.fixture(scope="module")
def people():
    """Two signed-in temporary users in one household; deleted afterwards (with their jobs)."""
    user_ids: list[str] = []
    people: dict[str, dict] = {}
    try:
        for name in ("a", "b"):
            password = secrets.token_urlsafe(16)
            email = f"jobs-test-{name}-{secrets.token_hex(3)}@example.com"
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
        call("DELETE", f"/rest/v1/worker_heartbeats?worker_id=eq.{WORKER_ID}", SECRET_KEY)


def send_test_job(person, **body):
    response = client.post("/api/me/jobs/test", json=body, headers=person["headers"])
    assert response.status_code == 200, response.text
    return response.json()


def job_row(job_id):
    status, rows = call("GET", f"/rest/v1/jobs?select=*&id=eq.{job_id}", SECRET_KEY)
    assert status == 200
    return rows[0]


def run_worker_until_empty():
    settings = WorkerSettings(
        supabase_url=URL,
        mac_worker_secret_key=SECRET_KEY,
        worker_id=WORKER_ID,
        ollama_url="http://127.0.0.1:9",  # not needed by the test job
    )
    asyncio.run(worker.run(settings, asyncio.Event(), once=True))


def test_quick_job_runs_on_vercel_without_queueing(people):
    job = send_test_job(people["a"], quick=True, message="fast")
    assert job["status"] == "done" and job["id"] is None
    assert job["result"]["processed_by"] == "vercel"


def test_queued_job_is_visible_to_the_household(people):
    a, b = people["a"], people["b"]
    job = send_test_job(a, message="queued")
    assert job["status"] == "pending" and job["id"]
    seen = client.get(f"/api/jobs/{job['id']}", headers=b["headers"])
    assert seen.status_code == 200 and seen.json()["status"] == "pending"
    a["queued_job"] = job["id"]


def test_people_cant_change_jobs_or_queue_for_others(people):
    a, b = people["a"], people["b"]
    job_id = a["queued_job"]
    call(
        "PATCH",
        f"/rest/v1/jobs?id=eq.{job_id}",
        PUBLISHABLE_KEY,
        a["token"],
        {"status": "done", "result": {"forged": True}},
    )
    assert job_row(job_id)["status"] == "pending"
    status, _ = call(
        "POST",
        "/rest/v1/jobs",
        PUBLISHABLE_KEY,
        b["token"],
        {"profile_id": a["profile_id"], "type": "test_echo"},
    )
    assert status in (401, 403)
    status, _ = call(
        "POST",
        "/rest/v1/rpc/claim_job",
        PUBLISHABLE_KEY,
        a["token"],
        {"p_worker_id": "sneaky", "p_mode": "local"},
    )
    assert status in (401, 403, 404)


def test_worker_runs_queued_jobs_and_reports_it_is_online(people):
    a = people["a"]
    run_worker_until_empty()
    row = job_row(a["queued_job"])
    assert row["status"] == "done"
    assert row["result"] == {"message": "queued", "processed_by": WORKER_ID, "attempt": 1}
    status = client.get("/api/worker-status", headers=a["headers"]).json()
    assert status["online"] is True


def test_failed_job_retried_by_its_owner_only(people):
    a, b = people["a"], people["b"]
    job = send_test_job(a, fail_times=10)
    # Use up the attempts quickly instead of waiting for the retry gaps.
    call("PATCH", f"/rest/v1/jobs?id=eq.{job['id']}", SECRET_KEY, body={"attempts": 2})
    run_worker_until_empty()
    failed = client.get(f"/api/jobs/{job['id']}", headers=a["headers"]).json()
    assert failed["status"] == "failed" and "Failing on purpose" in failed["last_error"]

    assert client.post(f"/api/me/jobs/{job['id']}/retry", headers=b["headers"]).status_code == 404
    retried = client.post(f"/api/me/jobs/{job['id']}/retry", headers=a["headers"])
    assert retried.status_code == 200
    assert retried.json()["status"] == "pending" and retried.json()["attempts"] == 0


def test_stuck_jobs_go_back_to_the_queue(people):
    a = people["a"]
    job = send_test_job(a)
    an_hour_ago = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    call(
        "PATCH",
        f"/rest/v1/jobs?id=eq.{job['id']}",
        SECRET_KEY,
        body={
            "status": "processing",
            "locked_by": "crashed-mac",
            "locked_at": an_hour_ago,
            "attempts": 1,
        },
    )
    status, count = call(
        "POST", "/rest/v1/rpc/requeue_stuck_jobs", SECRET_KEY, body={"p_stuck_after": "900 seconds"}
    )
    assert status == 200 and count >= 1
    row = job_row(job["id"])
    assert row["status"] == "pending" and row["locked_by"] is None


def test_signed_out_visitors_see_nothing():
    for table in ("jobs", "worker_heartbeats"):
        status, rows = call("GET", f"/rest/v1/{table}?select=*", PUBLISHABLE_KEY)
        assert status in (401, 403) or rows == []
