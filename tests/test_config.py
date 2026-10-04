"""Tests for configuration loading (no DB / network required)."""

from app.config import Settings


def test_settings_defaults_are_sane() -> None:
    settings = Settings(_env_file=None)

    assert settings.demo_mode is False
    assert settings.serpapi_daily_cap > 0
    assert settings.database_url.startswith("postgresql+psycopg://")


def test_cors_origins_are_split_and_trimmed() -> None:
    settings = Settings(_env_file=None, frontend_origins="http://a.example, http://b.example ,")

    assert settings.cors_origins == ["http://a.example", "http://b.example"]
