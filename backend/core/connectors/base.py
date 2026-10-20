"""What every connector provides, and helpers they share.

A connector knows one service's sign-in (OAuth) addresses, how to swap a code
or refresh key for access keys, and how to turn the service's data into our
measurements (`Sample`s, the same shape the iOS Shortcut sends).
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any, Protocol
from urllib.parse import urlencode
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx2


class ServiceAuthError(Exception):
    """The service refused our keys (revoked or expired): the person must reconnect."""


class ServiceError(Exception):
    """The service failed or answered unexpectedly; worth trying again later."""


@dataclass
class Tokens:
    access_token: str
    refresh_token: str | None
    expires_at: datetime | None
    external_user_id: str | None = None
    scopes: str | None = None


# One measurement: {"metric", "date" (ISO), "value"} or {"metric", "date", "at"}.
Sample = dict[str, Any]


class Connector(Protocol):
    service: str
    label: str
    authorize_url: str
    scopes: str

    def authorize_params(self, client_id: str, redirect_uri: str, state: str) -> dict[str, str]:
        """Query parameters for the service's sign-in page."""
        ...

    async def exchange_code(
        self, http: httpx2.AsyncClient, client: tuple[str, str], code: str, redirect_uri: str
    ) -> Tokens: ...

    async def refresh(
        self, http: httpx2.AsyncClient, client: tuple[str, str], tokens: Tokens
    ) -> Tokens: ...

    async def fetch(
        self, http: httpx2.AsyncClient, tokens: Tokens, start: date, end: date
    ) -> list[Sample]:
        """Measurements for the local days start..end (inclusive)."""
        ...

    async def revoke(
        self, http: httpx2.AsyncClient, client: tuple[str, str], tokens: Tokens
    ) -> None:
        """Ask the service to cancel our access, where it supports that."""
        ...


def sign_in_address(connector: Connector, client_id: str, redirect_uri: str, state: str) -> str:
    params = connector.authorize_params(client_id, redirect_uri, state)
    return f"{connector.authorize_url}?{urlencode(params)}"


def expires_in(seconds: Any) -> datetime | None:
    return datetime.now(UTC) + timedelta(seconds=int(seconds)) if seconds else None


def check_response(response: httpx2.Response) -> Any:
    """The JSON body, or ServiceAuthError / ServiceError."""
    if response.status_code in (401, 403):
        raise ServiceAuthError(f"{response.status_code}")
    if response.status_code == 400 and "grant" in response.text.lower():
        # e.g. "invalid_grant": a refresh key that was revoked or already used.
        raise ServiceAuthError("invalid_grant")
    if response.status_code >= 400:
        raise ServiceError(f"HTTP {response.status_code}")
    try:
        return response.json()
    except ValueError as error:
        raise ServiceError("Not JSON") from error


def number(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def minutes(seconds: Any) -> float | None:
    value = number(seconds)
    return round(value / 60) if value is not None else None


def zone(name: str | None) -> timezone | ZoneInfo:
    try:
        return ZoneInfo(name) if name else UTC
    except (ZoneInfoNotFoundError, ValueError):
        return UTC


def offset_zone(offset: str | None) -> timezone:
    """'+05:30' → that fixed offset (UTC if missing or malformed)."""
    try:
        sign = -1 if offset and offset.startswith("-") else 1
        hours, mins = (offset or "").lstrip("+-").split(":")
        return timezone(sign * timedelta(hours=int(hours), minutes=int(mins)))
    except ValueError:
        return UTC


def parse_time(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def value_sample(metric: str, day: date | str, value: float | None) -> Sample | None:
    if value is None:
        return None
    return {"metric": metric, "date": str(day), "value": value}


def time_sample(metric: str, day: date | str, at: datetime | None) -> Sample | None:
    if at is None:
        return None
    return {"metric": metric, "date": str(day), "at": at.isoformat()}


def keep(*samples: Sample | None) -> list[Sample]:
    return [sample for sample in samples if sample is not None]
