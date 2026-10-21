"""The job queue's rules and the worker's safeguards (core/jobs/, backend/worker/)."""

import asyncio
from datetime import UTC, datetime, timedelta

import httpx2
import pytest

from core.jobs import JOBS, JobContext, JobSpec, PermanentJobError, queue
from core.jobs.test_echo import run as echo
from worker import main as worker
from worker.config import WorkerSettings

NOW = datetime(2026, 10, 21, 9, 0, tzinfo=UTC)


def run(coroutine):
    return asyncio.run(coroutine)


def settings(**overrides) -> WorkerSettings:
    return WorkerSettings(
        supabase_url="https://example.supabase.co",
        mac_worker_secret_key="sb_secret_test",
        worker_id="test-mac",
        ollama_url="http://ollama.test",
        **overrides,
    )


def job(**overrides):
    return {
        "id": "job-1",
        "type": "test_echo",
        "payload": {"message": "hi"},
        "attempts": 1,
        "max_attempts": 3,
        **overrides,
    }


# --- Retries -------------------------------------------------------------------


def test_retries_wait_longer_each_time():
    assert worker.retry_delay(1) == timedelta(minutes=1)
    assert worker.retry_delay(2) == timedelta(minutes=5)
    assert worker.retry_delay(3) == timedelta(minutes=25)
    assert worker.retry_delay(9) == timedelta(hours=6)


def test_failed_attempt_is_retried_until_the_last_one():
    retry = worker.outcome_for_failure(job(attempts=1), "boom", False, NOW)
    assert retry["status"] == "pending"
    assert retry["run_after"] == (NOW + timedelta(minutes=1)).isoformat()
    assert retry["last_error"] == "boom" and retry["locked_by"] is None
    last = worker.outcome_for_failure(job(attempts=3), "boom", False, NOW)
    assert last["status"] == "failed" and last["finished_at"] == NOW.isoformat()
    permanent = worker.outcome_for_failure(job(attempts=1), "bad input", True, NOW)
    assert permanent["status"] == "failed"


# --- The test job ----------------------------------------------------------------


def test_echo_job_echoes_and_can_fail_on_purpose():
    ctx = JobContext(worker_id="mac", attempt=1, http=None)  # type: ignore[arg-type]
    assert run(echo({"message": "hi"}, ctx)) == {
        "message": "hi",
        "processed_by": "mac",
        "attempt": 1,
    }
    with pytest.raises(RuntimeError):
        run(echo({"fail_times": 1}, ctx))
    ctx.attempt = 2
    assert run(echo({"fail_times": 1}, ctx))["attempt"] == 2
    with pytest.raises(PermanentJobError):
        run(echo({"delay_seconds": 999}, ctx))


# --- Running a job in the worker --------------------------------------------------


class FakeDb:
    def __init__(self, jobs=()):
        self.jobs = list(jobs)
        self.updates: list[tuple[str, dict]] = []
        self.heartbeats = 0
        self.requeued = 0

    async def claim(self, worker_id, mode):
        return self.jobs.pop(0) if self.jobs else None

    async def update_job(self, job_id, values):
        self.updates.append((job_id, values))

    async def heartbeat(self, *args):
        self.heartbeats += 1

    async def requeue_stuck(self, seconds):
        self.requeued += 1
        return 0


def ollama(up: bool) -> httpx2.AsyncClient:
    return httpx2.AsyncClient(
        transport=httpx2.MockTransport(lambda request: httpx2.Response(200 if up else 503))
    )


def process(job_row, http=None):
    db = FakeDb()
    run(worker.process(db, http or ollama(True), settings(), job_row))
    [(job_id, values)] = db.updates
    return values


def test_a_successful_job_saves_its_result():
    values = process(job())
    assert values["status"] == "done"
    assert values["result"] == {"message": "hi", "processed_by": "test-mac", "attempt": 1}
    assert values["last_error"] is None and values["finished_at"]


def test_a_failing_job_goes_back_in_the_queue_with_the_error():
    values = process(job(payload={"fail_times": 5}))
    assert values["status"] == "pending"
    assert "Failing on purpose" in values["last_error"]


def test_unknown_job_types_fail_straight_away():
    assert process(job(type="mystery"))["status"] == "failed"


def test_jobs_that_take_too_long_count_as_failed(monkeypatch):
    async def slow(payload, ctx):
        await asyncio.sleep(1)
        return {}

    monkeypatch.setitem(JOBS, "slow", JobSpec(type="slow", handler=slow, timeout_seconds=0.01))
    values = process(job(type="slow", attempts=3))
    assert values["status"] == "failed"
    assert "longer than" in values["last_error"]


def test_jobs_needing_the_local_ai_wait_while_ollama_is_down(monkeypatch):
    async def read(payload, ctx):
        return {"ok": True}

    monkeypatch.setitem(JOBS, "local", JobSpec(type="local", handler=read, needs_ollama=True))
    waiting = process(job(type="local", attempts=1), http=ollama(False))
    assert waiting["status"] == "pending"
    assert waiting["attempts"] == 0  # not counted against the job
    assert "Ollama" in waiting["last_error"]
    assert process(job(type="local"), http=ollama(True))["status"] == "done"


def test_worker_beats_requeues_stuck_jobs_and_drains_the_queue(monkeypatch):
    db = FakeDb([job(id="a"), job(id="b")])
    monkeypatch.setattr(worker, "WorkerDb", lambda *args: db)

    async def go():
        await worker.run(settings(), asyncio.Event(), once=True)

    run(go())
    assert sorted(job_id for job_id, _ in db.updates) == ["a", "b"]
    assert db.heartbeats == 1 and db.requeued == 1


def test_worker_runs_jobs_side_by_side(monkeypatch):
    async def slow(payload, ctx):
        await asyncio.sleep(0.3)
        return {}

    monkeypatch.setitem(JOBS, "slow", JobSpec(type="slow", handler=slow))
    db = FakeDb([job(id=str(n), type="slow") for n in range(3)])
    monkeypatch.setattr(worker, "WorkerDb", lambda *args: db)

    async def go():
        started = asyncio.get_running_loop().time()
        await worker.run(settings(), asyncio.Event(), once=True)
        return asyncio.get_running_loop().time() - started

    elapsed = run(go())
    assert len(db.updates) == 3 and all(v["status"] == "done" for _, v in db.updates)
    assert elapsed < 0.8  # three 0.3 s jobs at once, not 0.9 s one after another


def test_worker_takes_at_most_its_limit_at_once(monkeypatch):
    active = 0
    peak = 0

    async def counted(payload, ctx):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.05)
        active -= 1
        return {}

    monkeypatch.setitem(JOBS, "counted", JobSpec(type="counted", handler=counted))
    db = FakeDb([job(id=str(n), type="counted") for n in range(7)])
    monkeypatch.setattr(worker, "WorkerDb", lambda *args: db)
    run(worker.run(settings(max_parallel_jobs=2), asyncio.Event(), once=True))
    assert len(db.updates) == 7 and peak == 2


# --- Vercel first, then queue -----------------------------------------------------


class FakeSupabase:
    def __init__(self):
        self.inserted = []

    async def insert(self, table, values, token, returning="*"):
        self.inserted.append(values)
        return [{"id": "queued-1", "status": "pending", "attempts": 0, **values}]


def test_quick_jobs_run_on_vercel_when_fast_enough():
    supabase = FakeSupabase()
    result = run(
        queue.run_now_or_queue(supabase, None, "token", "profile", "test_echo", {"message": "x"})
    )
    assert result.status == "done" and result.id is None
    assert result.result["processed_by"] == "vercel"
    assert supabase.inserted == []


def test_slow_or_failing_quick_jobs_are_queued_instead():
    supabase = FakeSupabase()
    slow = run(
        queue.run_now_or_queue(
            supabase,
            None,
            "token",
            "profile",
            "test_echo",
            {"delay_seconds": 1},
            budget_seconds=0.01,
        )
    )
    failing = run(
        queue.run_now_or_queue(supabase, None, "token", "profile", "test_echo", {"fail_times": 1})
    )
    assert slow.status == failing.status == "pending"
    assert [row["type"] for row in supabase.inserted] == ["test_echo", "test_echo"]


def test_local_only_jobs_are_never_run_on_vercel(monkeypatch):
    called = []

    async def read(payload, ctx):
        called.append(True)
        return {}

    monkeypatch.setitem(
        JOBS, "private", JobSpec(type="private", handler=read, local_only=True, try_on_vercel=True)
    )
    supabase = FakeSupabase()
    result = run(queue.run_now_or_queue(supabase, None, "token", "profile", "private", {}))
    assert result.status == "pending" and not called
    assert supabase.inserted[0]["local_only"] is True
