"""Visibility snapshot endpoint skeleton (PRD FR-13, section 10)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter

from app.core.data_loader import METHOD_NOTE, snapshot_grid
from app.schemas.search import CoverageResponse

router = APIRouter(tags=["coverage"])


@router.get("/coverage", response_model=CoverageResponse)
def get_coverage() -> CoverageResponse:
    languages, cities = snapshot_grid()
    rows = [
        {
            "language": lang,
            "city": city,
            "explicit_count": 0,
            "inferred_count": 0,
        }
        for lang in languages
        for city in cities
    ]
    return CoverageResponse(
        snapshot_date=date.today().isoformat(), method_note=METHOD_NOTE, rows=rows
    )
