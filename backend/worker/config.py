import socket
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    """The worker's configuration (locally from backend/.env)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str
    # The secret key named `mac-worker` in Supabase: one key per component, so
    # it can be replaced without touching the API or the tests.
    mac_worker_secret_key: str
    worker_id: str = socket.gethostname()
    worker_mode: Literal["local", "cloud"] = "local"
    ollama_url: str = "http://localhost:11434"
    # How often to look for work when the queue is empty.
    poll_seconds: float = 10
    heartbeat_seconds: float = 60
