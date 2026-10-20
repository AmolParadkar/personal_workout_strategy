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
        self, table: str, filters: dict[str, str], values: dict[str, Any], access_token: str
    ) -> list[dict[str, Any]]:
        """Update rows the user may change; returns the updated rows (empty if none allowed)."""
        response = await self._http.patch(
            f"{self._url}/rest/v1/{table}",
            params=filters,
            json=values,
            headers={**self._headers(access_token), "Prefer": "return=representation"},
        )
        self._check(response)
        return response.json()

    async def get_household_profiles(self, access_token: str) -> list[dict[str, Any]]:
        """Profiles the user is allowed to see (their household), oldest first."""
        return await self.select(
            "profiles",
            {"select": "id,user_id,display_name,onboarded_at", "order": "created_at"},
            access_token,
        )
