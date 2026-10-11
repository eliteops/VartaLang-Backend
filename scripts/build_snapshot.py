"""Visibility snapshot runner (PRD v1.2, FR-13, Oct 7).

One-time, dated 8 languages x 5 cities grid: 1 google_jobs page per pair
(~40 billable searches). Scores every listing with the production scorer,
splits into explicit / inferred, and writes `data/coverage_snapshot.json`
which the API serves from `GET /api/coverage`.

hl-fallback: the spike showed `mai` and `bho` are unsupported; the client
retries with `hl=en` when SerpApi reports "Unsupported".

Fast mode: runs pairs in a small thread pool (2 workers) with a 45 s
timeout and a single retry, so the full 40-pair grid finishes in ~1-2 min
instead of ~15.  A `--smoke` flag limits the grid to 2 languages x 3 cities
for a ~30 s pipeline check.

Run:  SERPAPI_KEY=... uv run python -m scripts.build_snapshot [--smoke]
Credit budget: ~40.  Check `SERPAPI_DAILY_CAP` before running.
"""

from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

from app.config import get_settings
from app.core.data_loader import snapshot_grid
from app.core.scoring import EXPLICIT, load_keywords, score_listing
from scripts.spike_serpapi import SerpApiClient

REPO_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_FILE = REPO_ROOT / "data" / "coverage_snapshot.json"
ROLE_TERMS = "translator OR interpreter OR transcription"
HTTP_TIMEOUT = 45.0
MAX_ATTEMPTS = 2
RETRY_BACKOFF = 1.0
WORKERS = 2

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

SMOKE_LANGS = ["hindi", "tamil"]
SMOKE_CITIES = ["delhi-ncr", "chennai", "kolkata"]


def _client(api_key: str) -> SerpApiClient:
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


def _process_pair(
    lang_id: str, lang_name: str, hl: str, city_id: str, location: str
) -> tuple[dict, dict | None]:
    """One thread-safe pair fetch + score. Returns (row, error|None)."""
    client = _client(get_settings().serpapi_key or "")
    try:
        page = _fetch_page(client, lang_name, location, hl)
        if "error" in page:
            return (
                {
                    "language": lang_id,
                    "city": city_id,
                    "explicit_count": 0,
                    "inferred_count": 0,
                },
                {"language": lang_id, "city": city_id, "error": str(page["error"])},
            )
        explicit, inferred = _score_pair(lang_id, page)
        return (
            {
                "language": lang_id,
                "city": city_id,
                "explicit_count": explicit,
                "inferred_count": inferred,
            },
            None,
        )
    finally:
        client.close()


def main() -> int:
    settings = get_settings()
    if not settings.serpapi_key:
        print("SERPAPI_KEY is not set (environment or .env). Add it and re-run.")
        return 1

    smoke = "--smoke" in sys.argv
    languages = SMOKE_LANGS if smoke else snapshot_grid()[0]
    cities = SMOKE_CITIES if smoke else snapshot_grid()[1]
    now = datetime.now(UTC).isoformat()

    tasks: list[tuple[str, str, str, str, str]] = []
    for lang_id in languages:
        lang_name, hl = LANG_META.get(lang_id, (lang_id.title(), "en"))
        for city_id in cities:
            location, display = CITY_META.get(city_id, (city_id.title(), city_id.title()))
            print(f"--- {lang_name} / {display} (hl={hl}) ---", flush=True)
            tasks.append((lang_id, lang_name, hl, city_id, location))

    rows: list[dict] = []
    errors: list[dict] = []
    billable = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(_process_pair, *t) for t in tasks]
        for fut in as_completed(futures):
            row, err = fut.result()
            rows.append(row)
            if err:
                errors.append(err)
                print(f"    {row['language']}/{row['city']}: error {err['error']}")
            else:
                print(
                    f"    {row['language']}/{row['city']}: "
                    f"explicit={row['explicit_count']} inferred={row['inferred_count']}"
                )

    # Second pass: retry failed pairs serially with a fresh client per pair.
    if errors and not smoke:
        print(f"\nRetrying {len(errors)} failed pairs serially...")
        errors2: list[dict] = []
        for err in list(errors):
            lang_id, city_id = err["language"], err["city"]
            lang_name, hl = LANG_META.get(lang_id, (lang_id.title(), "en"))
            location, _display = CITY_META.get(city_id, (city_id.title(), city_id.title()))
            print(f"    retry {lang_id}/{city_id} ...", flush=True)
            row2, err2 = _process_pair(lang_id, lang_name, hl, city_id, location)
            for i, r in enumerate(rows):
                if r["language"] == lang_id and r["city"] == city_id:
                    rows[i] = row2
                    break
            if err2:
                errors2.append(err2)
        errors = errors2

    snapshot = {
        "version": 1,
        "snapshot_date": now,
        "rows": rows,
        "errors": errors,
        "billable_searches": billable,
        "http_requests": len(tasks) * (MAX_ATTEMPTS) + len(errors),
    }
    SNAPSHOT_FILE.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"\nSnapshot written to {SNAPSHOT_FILE}")
    print(f"Rows: {len(rows)} ({len(errors)} with errors)")
    print(f"Billable (approx): {len(tasks)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
