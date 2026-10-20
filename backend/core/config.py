from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from the environment
