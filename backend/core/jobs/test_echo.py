"""`test_echo`: a job that does nothing useful, to check the queue end to end.

Settings → Mac worker → "Send test job" queues one. Options let the tests
exercise the safeguards: a delay (to test the Vercel time limit) and failing
the first few attempts (to test retries).
"""

import asyncio
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from core.jobs import JobContext, JobSpec, PermanentJobError, register


class TestEchoPayload(BaseModel):
    message: str = Field(default="Hello from the queue", max_length=200)
    delay_seconds: float = Field(default=0, ge=0, le=60)
    # Fail attempts 1..fail_times, then succeed.
    fail_times: int = Field(default=0, ge=0, le=10)


async def run(payload: dict[str, Any], ctx: JobContext) -> dict[str, Any]:
    try:
        job = TestEchoPayload.model_validate(payload)
    except ValidationError as error:
        raise PermanentJobError("Invalid test job") from error
    if job.delay_seconds:
        await asyncio.sleep(job.delay_seconds)
    if ctx.attempt <= job.fail_times:
        raise RuntimeError(f"Failing on purpose (attempt {ctx.attempt})")
    return {"message": job.message, "processed_by": ctx.worker_id, "attempt": ctx.attempt}


SPEC = register(
    JobSpec(type="test_echo", handler=run, try_on_vercel=True, max_attempts=3, timeout_seconds=90)
)
