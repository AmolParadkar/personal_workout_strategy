"""Calls to Supabase on behalf of a signed-in user.

Every call passes the user's own sign-in token, so Supabase's access rules
(see supabase/migrations/) decide what the user may read or change. The backend
never re-implements those rules.
"""

from typing import Any

import httpx2


class NotSignedInError(Exception):
    """The sign-in token is missing, expired or invalid."""


class InvalidValueError(Exception):
    """The database rejected a value (e.g. a check constraint or a required field)."""


class SupabaseClient:
    def __init__(self, url: str, publishable_key: str, http: httpx2.AsyncClient) -> None:
        self._url = url.rstrip("/")
        self._key = publishable_key
        self._http = http

    def _headers(self, access_token: str) -> dict[str, str]:
        return {"apikey": self._key, "Authorization": f"Bearer {access_token}"}

    @staticmethod
    def _check(response: httpx2.Response) -> None:
        if response.status_code in (401, 403):
            raise NotSignedInError
        if response.status_code == 400:
            raise InvalidValueError(response.json().get("message", "Invalid value"))
        response.raise_for_status()

    async def get_user_id(self, access_token: str) -> str:
        """Return the id of the user the token belongs to, after Supabase verifies it."""
        response = await self._http.get(
            f"{self._url}/auth/v1/user", headers=self._headers(access_token)
        )
        self._check(response)
        return response.json()["id"]

    async def select(
        self, table: str, params: dict[str, str], access_token: str
    ) -> list[dict[str, Any]]:
        """Read rows the user may see. `params` use Supabase's filter syntax."""
        response = await self._http.get(
            f"{self._url}/rest/v1/{table}", params=params, headers=self._headers(access_token)
        )
        self._check(response)
        return response.json()

    async def update(
        self,
        table: str,
        filters: dict[str, str],
        values: dict[str, Any],
        access_token: str,
        returning: str = "*",
    ) -> list[dict[str, Any]]:
        """Update rows the user may change; returns the updated rows' `returning` columns
        (empty if none allowed). Narrow it for tables where some columns are hidden."""
        response = await self._http.patch(
            f"{self._url}/rest/v1/{table}",
            params={**filters, "select": returning},
            json=values,
            headers={**self._headers(access_token), "Prefer": "return=representation"},
        )
        self._check(response)
        return response.json()

    async def insert(
        self, table: str, values: dict[str, Any], access_token: str, returning: str = "*"
    ) -> list[dict[str, Any]]:
        """Add a row the user is allowed to create; returns the `returning` columns
        (narrow it for tables where some columns are hidden from the user)."""
        response = await self._http.post(
            f"{self._url}/rest/v1/{table}",
            params={"select": returning},
            json=values,
            headers={**self._headers(access_token), "Prefer": "return=representation"},
        )
        self._check(response)
        return response.json()

    async def upsert(
        self, table: str, values: dict[str, Any], on_conflict: str, access_token: str
    ) -> None:
        """Add a row unless an identical one exists (then do nothing, so repeats are harmless)."""
        response = await self._http.post(
            f"{self._url}/rest/v1/{table}",
            params={"on_conflict": on_conflict},
            json=values,
            headers={
                **self._headers(access_token),
                "Prefer": "resolution=ignore-duplicates,return=minimal",
            },
        )
        self._check(response)

    async def delete(self, table: str, filters: dict[str, str], access_token: str) -> None:
        """Delete rows the user is allowed to delete (silently none if not allowed)."""
        response = await self._http.delete(
            f"{self._url}/rest/v1/{table}", params=filters, headers=self._headers(access_token)
        )
        self._check(response)

    async def rpc(
        self, function: str, args: dict[str, Any], access_token: str | None = None
    ) -> Any:
        """Call a database function. Without a token it runs as a signed-out caller."""
        headers = self._headers(access_token) if access_token else {"apikey": self._key}
        response = await self._http.post(
            f"{self._url}/rest/v1/rpc/{function}", json=args, headers=headers
        )
        self._check(response)
        # Functions that return nothing (void) reply with an empty body.
        return response.json() if response.content else None

    async def get_household_profiles(self, access_token: str) -> list[dict[str, Any]]:
        """Profiles the user is allowed to see (their household), oldest first,
        with any running 75 Hard challenge embedded."""
        return await self.select(
            "profiles",
            {
                "select": "id,user_id,display_name,onboarded_at,challenges(id)",
                "challenges.stopped_at": "is.null",
                "order": "created_at",
            },
            access_token,
        )
