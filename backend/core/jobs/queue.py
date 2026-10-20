"""The job queue, used by the API as the signed-in person.

The person can add jobs for themselves, see their household's jobs and retry
their own failed ones; everything else happens in the worker (backend/worker/).
"""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx2

from core.jobs import JOBS, JobContext, JobSpec
from core.models.jobs import Job, WorkerStatus
from core.supabase import SupabaseClient

JOB_COLUMNS = (
    "id,type,status,result,last_error,attempts,max_attempts,local_only,created_at,finished_at"
)
ONLINE_WITHIN = timedelta(minutes=3)
# Vercel stops a request after its time limit; give up well before that.
VERCEL_BUDGET_SECONDS = 20.0


class UnknownJobTypeError(Exception):
    pass


class JobNotFoundError(Exception):
    pass


def _spec(job_type: str) -> JobSpec:
    if job_type not in JOBS:
        raise UnknownJobTypeError(job_type)
    return JOBS[job_type]


async def enqueue(
    supabase: SupabaseClient,
    token: str,
    profile_id: str,
    job_type: str,
    payload: dict[str, Any],
    allow_cloud: bool = False,
) -> Job:
    spec = _spec(job_type)
    rows = await supabase.insert(
        "jobs",
        {
            "profile_id": profile_id,
            "type": job_type,
            "payload": payload,
            "local_only": spec.local_only,
            "allow_cloud": allow_cloud,
            "max_attempts": spec.max_attempts,
        },
        token,
        returning=JOB_COLUMNS,
    )
    return Job(**rows[0])


async def run_now_or_queue(
    supabase: SupabaseClient,
    http: httpx2.AsyncClient,
    token: str,
    profile_id: str,
    job_type: str,
    payload: dict[str, Any],
    budget_seconds: float = VERCEL_BUDGET_SECONDS,
) -> Job:
    """ "Vercel first, then queue": run a quick cloud job straight away; if it's too
    slow or fails, queue it for the worker instead. Local-only jobs always queue."""
    spec = _spec(job_type)
    if spec.try_on_vercel and not spec.local_only:
        ctx = JobContext(worker_id="vercel", attempt=1, http=http)
        try:
            result = await asyncio.wait_for(spec.handler(payload, ctx), budget_seconds)
            return Job(
                id=None,
                type=job_type,
                status="done",
                result=result,
                attempts=1,
                max_attempts=spec.max_attempts,
                finished_at=datetime.now(UTC),
            )
        except Exception:  # noqa: BLE001 - any failure here just means "queue it"
            pass
    return await enqueue(supabase, token, profile_id, job_type, payload)


async def get_job(supabase: SupabaseClient, token: str, job_id: str) -> Job:
    rows = await supabase.select("jobs", {"select": JOB_COLUMNS, "id": f"eq.{job_id}"}, token)
    if not rows:
        raise JobNotFoundError
    return Job(**rows[0])


async def retry(supabase: SupabaseClient, token: str, job_id: str) -> Job:
    """Put your own failed job back in the queue with fresh attempts."""
    try:
        await supabase.rpc("retry_job", {"p_job_id": job_id}, token)
    except httpx2.HTTPStatusError as error:
        # The database answers "not found" unless it's your own failed job.
        raise JobNotFoundError from error
    return await get_job(supabase, token, job_id)


async def worker_status(supabase: SupabaseClient, token: str) -> WorkerStatus:
    beats = await supabase.select(
        "worker_heartbeats",
        {"select": "last_seen_at,ollama_ok", "mode": "eq.local", "order": "last_seen_at.desc"},
        token,
    )
    waiting = await supabase.select(
        "jobs",
        {
            "select": "created_at",
            "status": "in.(pending,processing)",
            "order": "created_at",
        },
        token,
    )
    last_seen = datetime.fromisoformat(beats[0]["last_seen_at"]) if beats else None
    return WorkerStatus(
        online=last_seen is not None and datetime.now(UTC) - last_seen < ONLINE_WITHIN,
        last_seen_at=last_seen,
        ollama_ok=beats[0]["ollama_ok"] if beats else None,
        waiting_jobs=len(waiting),
        oldest_waiting_at=waiting[0]["created_at"] if waiting else None,
    )
