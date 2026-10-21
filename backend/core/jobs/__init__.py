"""Job types: what each queued job does and where it may run.

Every slow or LLM task is a job (context/architecture.md, "Job types"). Each
type is registered here with its rules; the worker and the "Vercel first"
helper look them up by name. Real job types arrive with their pages (M5+);
`test_echo` exists to prove the queue and worker work end to end.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

import httpx2

from core.llm import LlmConfig


class JobDb(Protocol):
    """Database access for jobs that read or write shared data (the worker's secret key)."""

    async def select(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]: ...

    async def update(self, table: str, filters: dict[str, str], values: dict[str, Any]) -> None: ...

    async def rpc(self, function: str, args: dict[str, Any]) -> Any: ...


@dataclass
class JobContext:
    # "vercel" when run straight away by the API, otherwise the worker's id.
    worker_id: str
    attempt: int
    http: httpx2.AsyncClient
    # Set by the worker; not available to jobs run on Vercel.
    db: JobDb | None = None
    llm: LlmConfig | None = None
    youtube_api_key: str | None = None


Handler = Callable[[dict[str, Any], JobContext], Awaitable[dict[str, Any]]]


class PermanentJobError(Exception):
    """The job can never succeed (e.g. bad input): fail now, don't retry."""


@dataclass(frozen=True)
class JobSpec:
    type: str
    handler: Handler
    # Health documents: only the Mac (local Ollama) may run them.
    local_only: bool = False
    # Quick cloud jobs: the API tries them straight away before queueing.
    try_on_vercel: bool = False
    # The worker checks Ollama answers before taking the job.
    needs_ollama: bool = False
    max_attempts: int = 3
    # How long one attempt may take before it counts as failed.
    timeout_seconds: float = 300


JOBS: dict[str, JobSpec] = {}


def register(spec: JobSpec) -> JobSpec:
    JOBS[spec.type] = spec
    return spec


# Imported for their register() calls.
from core.jobs import exercise_guide, exercise_video, test_echo, workout_plan  # noqa: E402, F401
