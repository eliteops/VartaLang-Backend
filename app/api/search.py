"""Search endpoint (PRD section 10: POST /api/search)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.api.rate_limit import limiter
from app.schemas.search import SearchRequest, SearchResponse
from app.services.search import run_search

router = APIRouter(tags=["search"])
INVALID_PAYLOAD = {
    "error": {"code": "invalid_input", "message": "Please check your inputs and try again."}
}


@router.post("/search")
@limiter.limit("30/minute")
def post_search(body: SearchRequest, request: Request):
    doc = run_search(body.language, body.location)
    if doc is None:
        return JSONResponse(status_code=422, content=INVALID_PAYLOAD)
    payload = SearchResponse(**doc)
    return JSONResponse(status_code=200, content=payload.model_dump(mode="json"))
