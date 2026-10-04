"""Application settings, loaded from environment variables and an optional `.env` file.

Secrets (the SerpApi key and the database URL) live ONLY here, on the server side.
They are never sent to the frontend and never committed to the repository.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    Every field can be overridden by an environment variable of the same name
    (case-insensitive) or by an entry in a local `.env` file. See `.env.example`.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- General ---
    app_name: str = "VartaLang Language Opportunity Radar"
    environment: str = "development"

    # When True the app serves seeded fixtures only: no API key, no upstream calls.
    demo_mode: bool = False

    # --- Database ---
    # Default points at the optional local Postgres (docker compose up -d postgres).
    # In production/dev set this to the Neon pooled connection string instead.
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/vartalang_radar"

    # --- SerpApi ---
    serpapi_key: str | None = None
    serpapi_daily_cap: int = 200
    serpapi_timeout_seconds: float = 10.0

    # --- Frontend / CORS ---
    # Comma-separated list of allowed origins for the Streamlit frontend.
    frontend_origins: str = "http://localhost:8501"

    @property
    def cors_origins(self) -> list[str]:
        """Return the CORS allowlist as a clean list of origins."""
        return [origin.strip() for origin in self.frontend_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a cached `Settings` instance (read once per process)."""
    return Settings()
