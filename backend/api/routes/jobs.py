from fastapi import APIRouter, HTTPException, status

from api.deps import CurrentUserDep, HttpDep, SupabaseDep
from core.jobs import queue
from core.models.jobs import Job, TestJobRequest, WorkerStatus
from core.profiles import own_profile_id

router = APIRouter(prefix="/api", tags=["jobs"])


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, user: CurrentUserDep, supabase: SupabaseDep) -> Job:
    """A job's status and, when done, its result (the household's jobs only)."""
    try:
        return await queue.get_job(supabase, user.access_token, job_id)
    except queue.JobNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found") from error


@router.post("/me/jobs/{job_id}/retry")
async def retry_job(job_id: str, user: CurrentUserDep, supabase: SupabaseDep) -> Job:
    """Put your own failed job back in the queue."""
    try:
        return await queue.retry(supabase, user.access_token, job_id)
    except queue.JobNotFoundError as error:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No failed job of yours with that id"
        ) from error


@router.get("/worker-status")
async def worker_status(user: CurrentUserDep, supabase: SupabaseDep) -> WorkerStatus:
    """Whether the Mac worker is online, and how many of the household's jobs wait."""
    return await queue.worker_status(supabase, user.access_token)


@router.post("/me/jobs/test")
async def test_job(
    body: TestJobRequest, user: CurrentUserDep, supabase: SupabaseDep, http: HttpDep
) -> Job:
    """Send a test job, to check the queue and worker work. With `quick`, it's
    tried on Vercel first and only queued if that's too slow."""
    profile_id = await own_profile_id(supabase, user.access_token, user.id)
    payload = body.model_dump(exclude={"quick"})
    if body.quick:
        return await queue.run_now_or_queue(
            supabase, http, user.access_token, profile_id, "test_echo", payload
        )
    return await queue.enqueue(supabase, user.access_token, profile_id, "test_echo", payload)
