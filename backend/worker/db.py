"""The worker's calls to Supabase, with the `mac-worker` secret key.

The secret key bypasses the access rules, which the worker needs to take any
person's job and write the result back. It's only on the Mac (backend/.env).
"""

from datetime import datetime
from typing import Any

import httpx2


class WorkerDb:
    def __init__(self, url: str, secret_key: str, http: httpx2.AsyncClient) -> None:
        self._url = url.rstrip("/")
        self._headers = {"apikey": secret_key}
        self._http = http

    async def _rpc(self, function: str, args: dict[str, Any]) -> Any:
        response = await self._http.post(
            f"{self._url}/rest/v1/rpc/{function}", json=args, headers=self._headers
        )
        response.raise_for_status()
        return response.json() if response.content else None

    async def claim(self, worker_id: str, mode: str) -> dict[str, Any] | None:
        rows = await self._rpc("claim_job", {"p_worker_id": worker_id, "p_mode": mode})
        return rows[0] if rows else None

    async def requeue_stuck(self, stuck_after_seconds: int) -> int:
        return await self._rpc(
            "requeue_stuck_jobs", {"p_stuck_after": f"{stuck_after_seconds} seconds"}
        )

    async def select(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        response = await self._http.get(
            f"{self._url}/rest/v1/{table}", params=params, headers=self._headers
        )
        response.raise_for_status()
        return response.json()

    async def update(self, table: str, filters: dict[str, str], values: dict[str, Any]) -> None:
        response = await self._http.patch(
            f"{self._url}/rest/v1/{table}",
            params=filters,
            json=values,
            headers={**self._headers, "Prefer": "return=minimal"},
        )
        response.raise_for_status()

    async def update_job(self, job_id: str, values: dict[str, Any]) -> None:
        response = await self._http.patch(
            f"{self._url}/rest/v1/jobs",
            params={"id": f"eq.{job_id}"},
            json=values,
            headers={**self._headers, "Prefer": "return=minimal"},
        )
        response.raise_for_status()

    async def heartbeat(
        self,
        worker_id: str,
        mode: str,
        version: str,
        ollama_ok: bool | None,
        started_at: datetime,
        now: datetime,
    ) -> None:
        response = await self._http.post(
            f"{self._url}/rest/v1/worker_heartbeats",
            params={"on_conflict": "worker_id"},
            json={
                "worker_id": worker_id,
                "mode": mode,
                "version": version,
                "ollama_ok": ollama_ok,
                "started_at": started_at.isoformat(),
                "last_seen_at": now.isoformat(),
            },
            headers={**self._headers, "Prefer": "resolution=merge-duplicates,return=minimal"},
        )
        response.raise_for_status()
