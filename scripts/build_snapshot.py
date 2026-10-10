"""Visibility snapshot runner (PRD v1.2, FR-13, Oct 7).

One-time, dated 8 languages x 5 cities grid: 1 google_jobs page per pair
(~40 billable searches). Scores every listing with the production scorer,
splits into explicit / inferred, and writes `data/coverage_snapshot.json`
which the API serves from `GET /api/coverage`.

hl-fallback: the spike showed `mai` and `bho` are unsupported; the client
retries with `hl=en` when SerpApi reports "Unsupported".

Run:  SERPAPI_KEY=... uv run python -m scripts.build_snapshot
Credit budget: ~40.  Check `SERPAPI_DAILY_CAP` before running.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from app.core.scoring import EXPLICIT, load_keywords, score_listing

from app.config import get_settings
from app.core.data_loader import snapshot_grid
from scripts.spike_serpapi import SerpApiClient

REPO_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_FILE = REPO_ROOT / "data" / "coverage_snapshot.json"
ROLE_TERMS = "translator OR interpreter OR transcription"
HTTP_TIMEOUT = 60.0
MAX_ATTEMPTS = 3
RETRY_BACKOFF = 2.0
SLEEP_BETWEEN = 0.6

# Language id -> (jobs query language, hl code). Maithili and Bhojpuri
# fall back to `hi` (spike finding: `mai` / `bho` unsupported).
LANG_META: dict[str, tuple[str, str]] = {
    "hindi": ("Hindi", "hi"),
    "tamil": ("Tamil", "ta"),
    "bengali": ("Bengali", "bn"),
    "maithili": ("Maithili", "hi"),
    "bhojpuri": ("Bhojpuri", "hi"),
    "telugu": ("Telugu", "te"),
    "marathi": ("Marathi", "mr"),
    "gujarati": ("Gujarati", "gu"),
}

# City id -> (jobs location string, display name). Matches `data/cities.json`.
CITY_META: dict[str, tuple[str, str]] = {
    "delhi-ncr": ("Delhi, India", "Delhi NCR"),
    "chennai": ("Chennai, India", "Chennai"),
    "kolkata": ("Kolkata, India", "Kolkata"),
    "patna": ("Patna, India", "Patna"),
    "lucknow": ("Lucknow, India", "Lucknow"),
}


def _client(api_key: str) -> SerpApiClient:
    # Reuse the spike client (retries, hl=en fallback, billable counting).
    return SerpApiClient(api_key, timeout=HTTP_TIMEOUT)


def _fetch_page(client: SerpApiClient, lang: str, location: str, hl: str) -> dict:
    params = {
        "q": f"{lang} {ROLE_TERMS}",
        "location": location,
        "gl": "in",
        "hl": hl,
    }
    last: dict = {"error": "unknown"}
    for attempt in range(MAX_ATTEMPTS):
        try:
            last = client.get("google_jobs", params)
        except Exception as exc:  # pragma: no cover - defensive
            last = {"error": f"client error: {type(exc).__name__}"}
        if "error" not in last:
            return last
        if "Unsupported" in str(last.get("error")) and hl != "en":
            params["hl"] = "en"
            hl = "en"
            continue
        if attempt + 1 < MAX_ATTEMPTS:
            time.sleep(RETRY_BACKOFF)
    return last


def _parse_listing(item: dict) -> dict:
    """Map one google_jobs result to the scorer's listing shape."""
    return {
        "title": item.get("title"),
        "company": item.get("company_name"),
        "location": item.get("location"),
        "snippet": item.get("description"),
        "posted_days_ago": None,
        "apply_link": item.get("link") or "",
    }


def _score_pair(lang_id: str, raw_page: dict) -> tuple[int, int]:
    kw = load_keywords(lang_id, data_dir=REPO_ROOT / "data" / "keywords")
    city_targets = {meta[0].split(",")[0] for meta in CITY_META.values()}
    explicit = inferred = 0
    for item in raw_page.get("jobs_results") or []:
        listing = _parse_listing(item)
        # Use the pair's target city from the listing location if present.
        target = listing.get("location") or ""
        if not any(c.casefold() in target.casefold() for c in city_targets):
            target = ""
        scored = score_listing(listing, kw, target or "India")
        if scored is None:
            continue
        if scored.label == EXPLICIT:
            explicit += 1
        else:
            inferred += 1
    return explicit, inferred


def main() -> int:
    settings = get_settings()
    if not settings.serpapi_key:
        print("SERPAPI_KEY is not set (environment or .env). Add it and re-run.")
        return 1

    languages, cities = snapshot_grid()
    client = _client(settings.serpapi_key)
    rows: list[dict] = []
    errors: list[dict] = []
    now = datetime.now(UTC).isoformat()

    try:
        for lang_id in languages:
            lang_name, hl = LANG_META.get(lang_id, (lang_id.title(), "en"))
            for city_id in cities:
                location, display = CITY_META.get(city_id, (city_id.title(), city_id.title()))
                print(f"--- {lang_name} / {display} (hl={hl}) ---", flush=True)
                page = _fetch_page(client, lang_name, location, hl)
                if "error" in page:
                    print(f"    error: {page['error']}")
                    errors.append(
                        {
                            "language": lang_id,
                            "city": city_id,
                            "error": str(page["error"]),
                        }
                    )
                    explicit = inferred = 0
                else:
                    explicit, inferred = _score_pair(lang_id, page)
                rows.append(
                    {
                        "language": lang_id,
                        "city": city_id,
                        "explicit_count": explicit,
                        "inferred_count": inferred,
                    }
                )
                print(f"    explicit={explicit} inferred={inferred}")
                time.sleep(SLEEP_BETWEEN)
    finally:
        client.close()

    snapshot = {
        "version": 1,
        "snapshot_date": now,
        "rows": rows,
        "errors": errors,
        "billable_searches": client.billable,
        "http_requests": client.requests,
    }
    SNAPSHOT_FILE.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"\nSnapshot written to {SNAPSHOT_FILE}")
    print(f"Billable searches: {client.billable}")
    print(f"Rows: {len(rows)} ({len(errors)} with errors)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
