import socket
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from core.llm import LlmConfig


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
    # Local Qwen model, the backup when Groq fails (`ollama pull qwen3:8b`).
    ollama_text_model: str = "qwen3:8b"
    # Cloud Qwen on Groq (console.groq.com → API Keys). Preview models change:
    # check console.groq.com/docs/models if Groq stops answering.
    groq_api_key: str | None = None
    groq_model: str = "qwen/qwen3.8-27b"
    # YouTube Data API v3 key (Google Cloud console), for exercise videos.
    youtube_api_key: str | None = None
    # How often to look for new jobs (each look is one small database request).
    poll_seconds: float = 3
    # Jobs run at the same time (e.g. an exercise's guide and its video).
    max_parallel_jobs: int = 3
    heartbeat_seconds: float = 60

    @property
    def llm(self) -> LlmConfig:
        return LlmConfig(
            groq_api_key=self.groq_api_key,
            groq_model=self.groq_model,
            ollama_url=self.ollama_url,
            ollama_model=self.ollama_text_model,
        )
