"""Visibility snapshot endpoint (PRD FR-13, section 10: `GET /api/coverage`).

Serves the dated snapshot written by `scripts/build_snapshot.py` when
`data/coverage_snapshot.json` exists; otherwise falls back to the zeroed
8x5 grid so the explorer always renders.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from fastapi import APIRouter

from app.core.data_loader import METHOD_NOTE, snapshot_grid
from app.schemas.search import CoverageResponse

router = APIRouter(tags=["coverage"])
SNAPSHOT_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "coverage_snapshot.json"


def _load_snapshot() -> dict | None:
    try:
        with SNAPSHOT_FILE.open(encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) and isinstance(doc.get("rows"), list) else None


@router.get("/coverage", response_model=CoverageResponse)
def get_coverage() -> CoverageResponse:
    languages, cities = snapshot_grid()
    grid = {(lang, city): (0, 0) for lang in languages for city in cities}
    snapshot_date = date.today().isoformat()

    snap = _load_snapshot()
    if snap:
        snapshot_date = str(snap.get("snapshot_date") or snapshot_date)[:10]
        for row in snap.get("rows", []):
            lang = row.get("language")
            city = row.get("city")
            if (lang, city) in grid:
                grid[(lang, city)] = (
                    int(row.get("explicit_count") or 0),
                    int(row.get("inferred_count") or 0),
                )

    rows = [
        {
            "language": lang,
            "city": city,
            "explicit_count": explicit,
            "inferred_count": inferred,
        }
        for (lang, city), (explicit, inferred) in grid.items()
    ]
    return CoverageResponse(snapshot_date=snapshot_date, method_note=METHOD_NOTE, rows=rows)
