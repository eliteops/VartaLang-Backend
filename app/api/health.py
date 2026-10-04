"""Liveness endpoint (FR / contract: `GET /api/health`)."""

from fastapi import APIRouter

from app import __version__

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Return a tiny payload confirming the API process is alive."""
    return {"status": "ok", "version": __version__}
