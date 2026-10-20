"""Connecting health services and fetching their data (context/data-sources.md,
"Connectors design").

Everything runs as the signed-in person: their keys are read and saved through
database functions that only touch their own connections, and the keys are
encrypted with CONNECTOR_ENCRYPTION_KEY before they reach the database.
"""

import asyncio
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlsplit

import httpx2

from core.config import Settings
from core.connectors import CONNECTORS
from core.connectors import keys as connector_keys
from core.connectors.base import ServiceAuthError, ServiceError, Tokens, sign_in_address
from core.health_data import validate_samples
from core.models.connections import (
    Connections,
    ServiceConnection,
    ServiceSyncResult,
    StartedConnection,
)
from core.supabase import SupabaseClient

FIRST_SYNC_DAYS = 30
# Re-fetch a couple of days before the last sync: services finish scoring
# sleep and activity late.
OVERLAP_DAYS = 2
AUTO_SYNC_EVERY = timedelta(hours=3)
REFRESH_MARGIN = timedelta(minutes=5)
SAVE_BATCH = 1000

STATUS_COLUMNS = "service,connected_at,last_synced_at,last_sync_error,needs_reconnect"


class UnknownServiceError(Exception):
    pass


class ServiceNotAvailableError(Exception):
    """The developer app's keys aren't set on the server yet."""


class BadRedirectError(Exception):
    """The return address isn't one of our websites' /connect/<service> pages."""


class ConnectFailedError(Exception):
    """The service didn't accept the sign-in code (expired, used, or refused)."""


def _connector(service: str):
    if service not in CONNECTORS:
        raise UnknownServiceError
    return CONNECTORS[service]


def _credentials(settings: Settings, service: str) -> tuple[str, str]:
    credentials = settings.connector_credentials(service)
    if credentials is None:
        raise ServiceNotAvailableError
    return credentials


def check_redirect(settings: Settings, service: str, redirect_uri: str) -> None:
    """Only our own websites (CORS_ORIGINS) may receive the sign-in code."""
    parts = urlsplit(redirect_uri)
    origin = f"{parts.scheme}://{parts.netloc}"
    if origin not in settings.cors_origin_list or parts.path != f"/connect/{service}":
        raise BadRedirectError
    if parts.query or parts.fragment:
        raise BadRedirectError


# --- Status --------------------------------------------------------------------


async def list_connections(
    supabase: SupabaseClient, settings: Settings, token: str, profile_id: str, can_edit: bool
) -> Connections:
    rows = await supabase.select(
        "service_connections",
        {"select": STATUS_COLUMNS, "profile_id": f"eq.{profile_id}"},
        token,
    )
    by_service = {row["service"]: row for row in rows}
    services = []
    for service, connector in CONNECTORS.items():
        row = by_service.get(service)
        services.append(
            ServiceConnection(
                service=service,  # type: ignore[arg-type]
                label=connector.label,
                available=settings.connector_credentials(service) is not None,
                connected=row is not None,
                **({k: row[k] for k in row if k != "service"} if row else {}),
            )
        )
    return Connections(services=services, can_edit=can_edit)


# --- Connecting ----------------------------------------------------------------


def start(
    settings: Settings, profile_id: str, service: str, redirect_uri: str
) -> StartedConnection:
    connector = _connector(service)
    client_id, _ = _credentials(settings, service)
    check_redirect(settings, service, redirect_uri)
    state = connector_keys.sign_state(settings.connector_encryption_key or "", profile_id, service)
    return StartedConnection(url=sign_in_address(connector, client_id, redirect_uri, state))


async def complete(
    supabase: SupabaseClient,
    http: httpx2.AsyncClient,
    settings: Settings,
    token: str,
    profile_id: str,
    service: str,
    code: str,
    state: str,
    redirect_uri: str,
    today: date,
) -> ServiceSyncResult:
    """Swap the sign-in code for keys, save them, then fetch the last 30 days."""
    connector = _connector(service)
    client = _credentials(settings, service)
    key = settings.connector_encryption_key or ""
    connector_keys.check_state(key, state, profile_id, service)
    check_redirect(settings, service, redirect_uri)
    try:
        tokens = await connector.exchange_code(http, client, code, redirect_uri)
    except (ServiceAuthError, ServiceError, httpx2.HTTPError, KeyError) as error:
        raise ConnectFailedError from error
    await _save_tokens(supabase, token, key, service, tokens)
    return await _sync_one(
        supabase, http, settings, token, profile_id, service, tokens, None, today
    )


async def _save_tokens(
    supabase: SupabaseClient, token: str, key: str, service: str, tokens: Tokens
) -> None:
    await supabase.rpc(
        "save_service_connection",
        {
            "p_service": service,
            "p_external_user_id": tokens.external_user_id,
            "p_access_token_enc": connector_keys.encrypt(key, tokens.access_token),
            "p_refresh_token_enc": (
                connector_keys.encrypt(key, tokens.refresh_token) if tokens.refresh_token else None
            ),
            "p_expires_at": tokens.expires_at.isoformat() if tokens.expires_at else None,
            "p_scopes": tokens.scopes,
        },
        token,
    )


async def _stored(
    supabase: SupabaseClient, token: str, key: str
) -> dict[str, tuple[Tokens, datetime | None]]:
    """The caller's connections: decrypted keys and when each last synced."""
    rows = await supabase.rpc("my_service_connection_keys", {}, token)
    stored = {}
    for row in rows:
        try:
            tokens = Tokens(
                access_token=connector_keys.decrypt(key, row["access_token_enc"]),
                refresh_token=(
                    connector_keys.decrypt(key, row["refresh_token_enc"])
                    if row["refresh_token_enc"]
                    else None
                ),
                expires_at=_time(row["expires_at"]),
                external_user_id=row["external_user_id"],
            )
        except ValueError:
            # Encrypted with a different key: treat as needing a reconnect.
            tokens = Tokens(
                access_token="", refresh_token=None, expires_at=datetime.min.replace(tzinfo=UTC)
            )
        stored[row["service"]] = (tokens, _time(row["last_synced_at"]))
    return stored


def _time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


async def disconnect(
    supabase: SupabaseClient,
    http: httpx2.AsyncClient,
    settings: Settings,
    token: str,
    profile_id: str,
    service: str,
) -> None:
    """Cancel access at the service where possible, then delete our copy of the keys."""
    _connector(service)
    key = settings.connector_encryption_key
    credentials = settings.connector_credentials(service)
    if key and credentials:
        stored = (await _stored(supabase, token, key)).get(service)
        if stored and stored[0].access_token:
            try:
                await CONNECTORS[service].revoke(http, credentials, stored[0])
            except (ServiceAuthError, ServiceError, httpx2.HTTPError):
                pass  # Deleting our keys is what matters.
    await supabase.delete(
        "service_connections",
        {"profile_id": f"eq.{profile_id}", "service": f"eq.{service}"},
        token,
    )


# --- Syncing -------------------------------------------------------------------


def sync_window(today: date, last_synced_at: datetime | None) -> tuple[date, date]:
    earliest = today - timedelta(days=FIRST_SYNC_DAYS - 1)
    if last_synced_at is None:
        return earliest, today
    return max(earliest, last_synced_at.date() - timedelta(days=OVERLAP_DAYS)), today


def is_due(last_synced_at: datetime | None, now: datetime, force: bool) -> bool:
    return force or last_synced_at is None or now - last_synced_at >= AUTO_SYNC_EVERY


async def sync(
    supabase: SupabaseClient,
    http: httpx2.AsyncClient,
    settings: Settings,
    token: str,
    profile_id: str,
    today: date,
    force: bool,
    only: str | None = None,
) -> list[ServiceSyncResult]:
    """Fetch new data from each of the caller's connections that is due (all, if
    forced), or from just `only`."""
    key = settings.connector_encryption_key
    if not key:
        return []
    stored = await _stored(supabase, token, key)
    now = datetime.now(UTC)
    jobs = []
    results = []
    for service, (tokens, last_synced_at) in stored.items():
        if only and service != only:
            continue
        if settings.connector_credentials(service) is None or not is_due(
            last_synced_at, now, force
        ):
            results.append(ServiceSyncResult(service=service, saved=0, skipped=True))  # type: ignore[arg-type]
            continue
        jobs.append(
            _sync_one(
                supabase, http, settings, token, profile_id, service, tokens, last_synced_at, today
            )
        )
    return results + list(await asyncio.gather(*jobs))


async def _sync_one(
    supabase: SupabaseClient,
    http: httpx2.AsyncClient,
    settings: Settings,
    token: str,
    profile_id: str,
    service: str,
    tokens: Tokens,
    last_synced_at: datetime | None,
    today: date,
) -> ServiceSyncResult:
    connector = CONNECTORS[service]
    client = _credentials(settings, service)
    status_filter = {"profile_id": f"eq.{profile_id}", "service": f"eq.{service}"}
    try:
        if not tokens.access_token or (
            tokens.expires_at and tokens.expires_at - REFRESH_MARGIN <= datetime.now(UTC)
        ):
            tokens = await connector.refresh(http, client, tokens)
            # Saved straight away: some services' refresh keys work only once.
            await _save_tokens(
                supabase, token, settings.connector_encryption_key or "", service, tokens
            )
        start, end = sync_window(today, last_synced_at)
        raw = await connector.fetch(http, tokens, start, end)
    except ServiceAuthError:
        message = f"{connector.label} no longer accepts our access. Connect again."
        await supabase.update(
            "service_connections",
            status_filter,
            {"needs_reconnect": True, "last_sync_error": message},
            token,
            returning="service",
        )
        return ServiceSyncResult(service=service, saved=0, error=message)  # type: ignore[arg-type]
    except (ServiceError, httpx2.HTTPError, KeyError, TypeError, ValueError):
        message = f"Couldn’t fetch from {connector.label}. Will try again later."
        await supabase.update(
            "service_connections",
            status_filter,
            {"last_sync_error": message},
            token,
            returning="service",
        )
        return ServiceSyncResult(service=service, saved=0, error=message)  # type: ignore[arg-type]

    # Same checks as the Shortcut's data: anything out of range is dropped.
    valid, _skipped = validate_samples(raw)
    samples = [s.model_dump(mode="json", exclude_none=True) for s in valid]
    saved = 0
    for i in range(0, len(samples), SAVE_BATCH):
        saved += await supabase.rpc(
            "save_service_samples",
            {"p_service": service, "p_samples": samples[i : i + SAVE_BATCH]},
            token,
        )
    await supabase.update(
        "service_connections",
        status_filter,
        {"last_synced_at": datetime.now(UTC).isoformat(), "last_sync_error": None},
        token,
        returning="service",
    )
    return ServiceSyncResult(service=service, saved=saved)  # type: ignore[arg-type]
