"""Allowlist endpoint (PRD section 10: `GET /api/languages`)."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.data_loader import get_languages_doc, list_languages
from app.schemas.search import LanguagesResponse

router = APIRouter(tags=["languages"])


@router.get("/languages", response_model=LanguagesResponse)
def get_languages() -> LanguagesResponse:
    """Return the supported-language allowlist from `data/languages.json`."""
    doc = get_languages_doc()
    return LanguagesResponse(version=int(doc.get("version", 1)), languages=list_languages())
