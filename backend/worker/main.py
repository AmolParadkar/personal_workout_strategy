"""The Mac worker: takes jobs from the queue, runs them and writes back results.

Run it with `uv run python -m worker` in backend/ (launchd keeps it running:
see backend/worker/launchd/). Safeguards (context/architecture.md):

- jobs are claimed atomically, so two workers never run the same one;
- failures are retried with growing gaps (1, 5, 25 … minutes), then marked failed;
- jobs left in `processing` (the Mac slept or crashed) go back to the queue;
- a heartbeat every minute lets the app show "offline since …";
- jobs needing the local AI wait while Ollama isn't answering.
"""

import asyncio
import logging
import signal
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx2

from core import __version__
from core.jobs import JOBS, JobContext, PermanentJobError
from worker.config import WorkerSettings
from worker.db import WorkerDb

log = logging.getLogger("worker")

# Longer than any job's own time limit, so only truly abandoned jobs are taken back.
STUCK_AFTER_SECONDS = 15 * 60
OLLAMA_WAIT = timedelta(minutes=5)


def retry_delay(attempt: int) -> timedelta:
    """1 minute after the first failure, then 5, 25, … (at most 6 hours)."""
    return min(timedelta(minutes=5 ** (attempt - 1)), timedelta(hours=6))


def outcome_for_failure(job: dict[str, Any], error: str, permanent: bool, now: datetime) -> dict:
    """What to write back after a failed attempt: try again later, or give up."""
    common = {"last_error": error[:1000], "locked_by": None, "locked_at": None}
    if permanent or job["attempts"] >= job["max_attempts"]:
        return {**common, "status": "failed", "finished_at": now.isoformat()}
    return {
        **common,
        "status": "pending",
        "run_after": (now + retry_delay(job["attempts"])).isoformat(),
    }


async def ollama_answers(http: httpx2.AsyncClient, url: str) -> bool:
    try:
        response = await http.get(f"{url.rstrip('/')}/api/version", timeout=5)
        return response.status_code == 200
    except httpx2.HTTPError:
        return False


async def process(db: WorkerDb, http: httpx2.AsyncClient, settings: WorkerSettings, job: dict):
    spec = JOBS.get(job["type"])
    now = datetime.now(UTC)
    if spec is None:
        log.error("Job %s has unknown type %s", job["id"], job["type"])
        await db.update_job(
            job["id"],
            outcome_for_failure(job, f"Unknown job type {job['type']}", True, now),
        )
        return
    if spec.needs_ollama and not await ollama_answers(http, settings.ollama_url):
        # Not the job's fault: put it back without using up an attempt.
        log.warning("Ollama isn't answering; job %s waits", job["id"])
        await db.update_job(
            job["id"],
            {
                "status": "pending",
                "attempts": job["attempts"] - 1,
                "run_after": (now + OLLAMA_WAIT).isoformat(),
                "locked_by": None,
                "locked_at": None,
                "last_error": "Waiting for the local AI (Ollama) to start.",
            },
        )
        return

    ctx = JobContext(
        worker_id=settings.worker_id,
        attempt=job["attempts"],
        http=http,
        db=db,
        llm=settings.llm,
        youtube_api_key=settings.youtube_api_key,
    )
    log.info("Running %s %s (attempt %s)", job["type"], job["id"], job["attempts"])
    try:
        result = await asyncio.wait_for(spec.handler(job["payload"], ctx), spec.timeout_seconds)
    except TimeoutError:
        values = outcome_for_failure(
            job, f"Took longer than {spec.timeout_seconds:g} seconds.", False, datetime.now(UTC)
        )
    except PermanentJobError as error:
        values = outcome_for_failure(job, str(error), True, datetime.now(UTC))
    except Exception as error:  # noqa: BLE001 - any other failure is retried
        log.exception("Job %s failed", job["id"])
        values = outcome_for_failure(
            job, str(error) or type(error).__name__, False, datetime.now(UTC)
        )
    else:
        values = {
            "status": "done",
            "result": result,
            "last_error": None,
            "locked_by": None,
            "locked_at": None,
            "finished_at": datetime.now(UTC).isoformat(),
        }
    await db.update_job(job["id"], values)
    log.info("Job %s → %s", job["id"], values["status"])


async def _process_safely(db: WorkerDb, http, settings: WorkerSettings, job: dict) -> None:
    try:
        await process(db, http, settings, job)
    except httpx2.HTTPError as error:
        # The result couldn't be saved; the job is taken back after
        # STUCK_AFTER_SECONDS and run again.
        log.warning("Couldn't save job %s (%s)", job["id"], error)


async def run(settings: WorkerSettings, stop: asyncio.Event, once: bool = False) -> None:
    """Work until `stop` is set (or, with `once`, until the queue is empty).

    Up to `max_parallel_jobs` jobs run at the same time (e.g. an exercise's guide
    and video side by side); the heartbeat keeps going while they run."""
    started_at = datetime.now(UTC)
    running: set[asyncio.Task] = set()
    async with httpx2.AsyncClient(timeout=30) as http:
        db = WorkerDb(settings.supabase_url, settings.mac_worker_secret_key, http)
        last_beat: datetime | None = None
        while not stop.is_set():
            now = datetime.now(UTC)
            try:
                if (
                    last_beat is None
                    or (now - last_beat).total_seconds() >= settings.heartbeat_seconds
                ):
                    ollama_ok = await ollama_answers(http, settings.ollama_url)
                    await db.heartbeat(
                        settings.worker_id,
                        settings.worker_mode,
                        __version__,
                        ollama_ok,
                        started_at,
                        now,
                    )
                    requeued = await db.requeue_stuck(STUCK_AFTER_SECONDS)
                    if requeued:
                        log.warning("Put %s stuck job(s) back in the queue", requeued)
                    last_beat = now
                while len(running) < settings.max_parallel_jobs:
                    job = await db.claim(settings.worker_id, settings.worker_mode)
                    if not job:
                        break
                    running.add(asyncio.create_task(_process_safely(db, http, settings, job)))
            except httpx2.HTTPError as error:
                # No internet or Supabase unavailable: wait and try again.
                log.warning("Can't reach Supabase (%s); retrying", error)
            if once and not running:
                return
            # Wake up when a job finishes (to take the next one), when told to
            # stop, or after `poll_seconds` to look for new jobs.
            stopping = asyncio.create_task(stop.wait())
            done, _ = await asyncio.wait(
                running | {stopping},
                timeout=settings.poll_seconds,
                return_when=asyncio.FIRST_COMPLETED,
            )
            stopping.cancel()
            running -= done
        if running:
            # Stopping (e.g. launchd at shutdown): let the current jobs finish.
            await asyncio.wait(running)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # Every request would otherwise be logged (a check every 10 seconds).
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = WorkerSettings()  # type: ignore[call-arg]  # values come from the environment
    log.info("Worker %s starting (mode %s)", settings.worker_id, settings.worker_mode)

    async def start() -> None:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        # launchd stops the worker with SIGTERM: finish the current job first.
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)
        await run(settings, stop)

    asyncio.run(start())
    log.info("Worker stopped")
