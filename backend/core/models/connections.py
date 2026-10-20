"""Direct connections to health services (Withings, Oura, Whoop, Polar)."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

Service = Literal["withings", "oura", "whoop", "polar"]


class ServiceConnection(BaseModel):
    service: Service
    label: str
    # False until the developer app's keys are set on the server.
    available: bool
    connected: bool
    connected_at: datetime | None = None
    last_synced_at: datetime | None = None
    last_sync_error: str | None = None
    # The service refused our keys: connect again.
    needs_reconnect: bool = False


class Connections(BaseModel):
    services: list[ServiceConnection]
    can_edit: bool


class StartConnection(BaseModel):
    # The website page the service sends the person back to: <website>/connect/<service>.
    redirect_uri: str = Field(max_length=300)


class StartedConnection(BaseModel):
    # The service's sign-in page, with our signed `state`.
    url: str


class CompleteConnection(BaseModel):
    code: str = Field(min_length=1, max_length=2000)
    state: str = Field(min_length=1, max_length=500)
    redirect_uri: str = Field(max_length=300)
    # The person's local date, so the first fetch covers the right days.
    today: date


class SyncRequest(BaseModel):
    today: date
    # Sync even if the last sync was recent (Refresh, "Sync now").
    force: bool = False
    # Just this service ("Sync now" on one service); all of them if empty.
    service: Service | None = None


class ServiceSyncResult(BaseModel):
    service: Service
    saved: int
    skipped: bool = False
    error: str | None = None


class SyncResult(BaseModel):
    results: list[ServiceSyncResult]
    connections: Connections
