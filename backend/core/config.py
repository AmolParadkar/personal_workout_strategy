from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from core.llm import LlmConfig


class Settings(BaseSettings):
    """Configuration from environment variables (locally from backend/.env)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str
    # Public key, used with a signed-in user's token so Supabase's access rules apply.
    supabase_publishable_key: str
    # Bypasses all access rules; only for backend jobs that genuinely need it.
    # Optional: the API doesn't use it yet, so it isn't uploaded to Vercel.
    supabase_secret_key: str | None = None
    # Comma-separated website addresses allowed to call the API.
    cors_origins: str = "http://localhost:8081"

    # Direct connectors (context/data-sources.md). A service can only be
    # connected once its developer app's client ID and secret are set.
    # Encrypts the services' access keys before they're stored; only the API has it.
    connector_encryption_key: str | None = None
    withings_client_id: str | None = None
    withings_client_secret: str | None = None
    oura_client_id: str | None = None
    oura_client_secret: str | None = None
    whoop_client_id: str | None = None
    whoop_client_secret: str | None = None
    polar_client_id: str | None = None
    polar_client_secret: str | None = None

    # Cloud Qwen on Groq, for quick plan generation on Vercel (the Mac worker has
    # its own copy). Without it, plans are made by the worker.
    groq_api_key: str | None = None
    groq_model: str = "qwen/qwen3.8-27b"

    @property
    def llm(self) -> LlmConfig:
        # No Ollama on Vercel: the worker is the backup.
        return LlmConfig(self.groq_api_key, self.groq_model, None, "")

    def connector_credentials(self, service: str) -> tuple[str, str] | None:
        """The developer app's client ID and secret, or None if not set up."""
        client_id = getattr(self, f"{service}_client_id", None)
        client_secret = getattr(self, f"{service}_client_secret", None)
        if not (client_id and client_secret and self.connector_encryption_key):
            return None
        return client_id, client_secret

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from the environment
