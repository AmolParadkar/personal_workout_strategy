"""Calls to Supabase on behalf of a signed-in user.

Every call passes the user's own sign-in token, so Supabase's access rules
(see supabase/migrations/) decide what the user may read or change. The backend
never re-implements those rules.
"""

from typing import Any

import httpx2


class NotSignedInError(Exception):
    """The sign-in token is missing, expired or invalid."""


class SupabaseClient:
    def __init__(self, url: str, publishable_key: str, http: httpx2.AsyncClient) -> None:
        self._url = url.rstrip("/")
        self._key = publishable_key
        self._http = http

    def _headers(self, access_token: str) -> dict[str, str]:
        return {"apikey": self._key, "Authorization": f"Bearer {access_token}"}

    async def get_user_id(self, access_token: str) -> str:
        """Return the id of the user the token belongs to, after Supabase verifies it."""
        response = await self._http.get(
            f"{self._url}/auth/v1/user", headers=self._headers(access_token)
        )
        if response.status_code in (401, 403):
            raise NotSignedInError
        response.raise_for_status()
        return response.json()["id"]

    async def get_household_profiles(self, access_token: str) -> list[dict[str, Any]]:
        """Profiles the user is allowed to see (their household), oldest first."""
        response = await self._http.get(
            f"{self._url}/rest/v1/profiles",
            params={"select": "id,user_id,display_name", "order": "created_at"},
            headers=self._headers(access_token),
        )
        if response.status_code in (401, 403):
            raise NotSignedInError
        response.raise_for_status()
        return response.json()
