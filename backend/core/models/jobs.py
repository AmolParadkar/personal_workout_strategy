"""The job queue as the website sees it: job status and the Mac worker's status."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

JobStatus = Literal["pending", "processing", "done", "failed"]


class Job(BaseModel):
    # Empty when the job ran straight away on Vercel and was never queued.
    id: str | None
    type: str
    status: JobStatus
    result: dict[str, Any] | None = None
    last_error: str | None = None
    attempts: int = 0
    max_attempts: int = 3
    local_only: bool = False
    created_at: datetime | None = None
    finished_at: datetime | None = None


class WorkerStatus(BaseModel):
    # Seen in the last 3 minutes.
    online: bool
    last_seen_at: datetime | None
    ollama_ok: bool | None
    # The household's jobs waiting or running.
    waiting_jobs: int
    oldest_waiting_at: datetime | None


class TestJobRequest(BaseModel):
    message: str = Field(default="Hello from the queue", max_length=200)
    # Try on Vercel first (falls back to the queue if too slow).
    quick: bool = False
    delay_seconds: float = Field(default=0, ge=0, le=60)
    fail_times: int = Field(default=0, ge=0, le=10)
