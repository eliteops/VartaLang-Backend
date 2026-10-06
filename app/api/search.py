"""Search endpoint skeleton (PRD section 10: `POST /api/search`).

Oct-4 scope: validate (FR-1), allowlist check, location normalize, and return
the section-10 contract shape with empty results + trust notice (FR-9).
Live SerpApi wiring, scoring, cache/budget land next; the shape stays stable.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.api.rate_limit import limiter
from app.config import get_settings
from app.core.data_loader import TRUST_NOTICE, normalize_location, resolve_language
from app.schemas.search import SearchRequest, SearchResponse

router = APIRouter(tags=["search"])
INVALID_PAYLOAD = {
    "error": {"code": "invalid_input", "message": "Please check your inputs and try again."}
}


@router.post("/search")
@limiter.limit("30/minute")
def post_search(body: SearchRequest, request: Request):
    lang = resolve_language(body.language)
    if lang is None:
        return JSONResponse(status_code=422, content=INVALID_PAYLOAD)
    settings = get_settings()
    now = datetime.now(UTC).isoformat()
    payload = SearchResponse(
        meta={
            "source": "fallback",
            "fetched_at": now,
            "daily_budget_remaining": settings.serpapi_daily_cap,
            "visibility": {"explicit": 0, "inferred": 0},
        },
        listings=[],
        providers=[],
        notice=TRUST_NOTICE,
    )
    _ = normalize_location(body.location)
    return JSONResponse(status_code=200, content=payload.model_dump(mode="json"))
