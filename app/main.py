"""FastAPI application factory and ASGI entrypoint.

Run locally with:  uv run uvicorn app.main:app --reload
"""

from fastapi import FastAPI

from app import __version__
from app.api.health import router as health_router
from app.config import get_settings


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    # All API routes live under /api.
    app.include_router(health_router, prefix="/api")

    return app


app = create_app()
