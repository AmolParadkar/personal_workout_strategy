"""Shared FastAPI dependencies: the Supabase client and the signed-in user."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

import httpx2
from fastapi import Depends, Header, HTTPException, status

from core.config import get_settings
from core.supabase import NotSignedInError, SupabaseClient


async def get_supabase() -> AsyncIterator[SupabaseClient]:
    settings = get_settings()
    async with httpx2.AsyncClient(timeout=15) as http:
        yield SupabaseClient(settings.supabase_url, settings.supabase_publishable_key, http)


@dataclass
class CurrentUser:
    id: str
    access_token: str


async def get_current_user(
    supabase: Annotated[SupabaseClient, Depends(get_supabase)],
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    """Require a valid Supabase sign-in token in the Authorization header."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    token = authorization.split(" ", 1)[1]
    try:
        user_id = await supabase.get_user_id(token)
    except NotSignedInError as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in") from error
    return CurrentUser(id=user_id, access_token=token)


SupabaseDep = Annotated[SupabaseClient, Depends(get_supabase)]
CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
