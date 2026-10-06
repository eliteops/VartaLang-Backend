"""Day-1 SerpApi spike (throwaway validation script).

Validates that `google_jobs` and `google_maps` return usable data for the five
demo pairs, saves raw responses as fixtures, and reports counts + credits.

Findings so far (recorded during the first run):
- google_jobs cold searches can take >10s; SerpApi caches identical searches,
  so repeats are instant and only real searches are billed.
- `hl=mai` (Maithili) and `hl=bho` (Bhojpuri) are rejected as unsupported;
  fall back to `hi` for those pairs.

Run:  uv run python -m scripts.spike_serpapi
Requires SERPAPI_KEY in the environment (or `.env`). The key is never printed.
"""

import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from app.config import get_settings

SERPAPI_URL = "https://serpapi.com/search.json"
REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "fixtures"

HTTP_TIMEOUT = 60.0
MAX_ATTEMPTS = 2
RETRY_BACKOFF = 2.0

ROLE_TERMS = "translator OR interpreter OR transcription"
MAPS_QUERIES = ["translation services", "transcription services"]
MIN_LISTINGS = 5
MIN_PROVIDERS = 5

# `hl` is the interface language we request. `hl_requested` records the language's
# own code, which may be unsupported (e.g. mai, bho) and thus replaced by `hi`.
PAIRS: list[dict[str, Any]] = [
    {
        "language": "Hindi",
        "hl": "hi",
        "hl_requested": "hi",
        "city": "Delhi NCR",
        "location": "Delhi, India",
        "lat": 28.6139,
        "lng": 77.2090,
    },
    {
        "language": "Tamil",
        "hl": "ta",
        "hl_requested": "ta",
        "city": "Chennai",
        "location": "Chennai, India",
        "lat": 13.0827,
        "lng": 80.2707,
    },
    {
        "language": "Bengali",
        "hl": "bn",
        "hl_requested": "bn",
        "city": "Kolkata",
        "location": "Kolkata, India",
        "lat": 22.5726,
        "lng": 88.3639,
    },
    {
        "language": "Maithili",
        "hl": "hi",
        "hl_requested": "mai",
        "city": "Patna",
        "location": "Patna, India",
        "lat": 25.5941,
        "lng": 85.1376,
    },
    {
        "language": "Bhojpuri",
        "hl": "hi",
        "hl_requested": "bho",
        "city": "Lucknow",
        "location": "Lucknow, India",
        "lat": 26.8467,
        "lng": 80.9462,
    },
]


def slug(text: str) -> str:
    """Lowercase, keep alphanumerics, collapse everything else to underscores."""
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in text.lower())
    return "_".join(part for part in cleaned.split("_") if part)


class SerpApiClient:
    """Minimal SerpApi client with retries and hl-fallback.

    Tracks `requests` (HTTP attempts) and `billable` (responses that ran a real
    search, i.e. returned `search_metadata`). Timed-out calls are not billed.
    """

    def __init__(self, api_key: str, timeout: float = HTTP_TIMEOUT) -> None:
        self._key = api_key
        self._client = httpx.Client(timeout=timeout)
        self.requests = 0
        self.billable = 0

    def get(self, engine: str, params: dict[str, Any]) -> dict[str, Any]:
        query = {"engine": engine, "api_key": self._key, "output": "json", **params}
        last_error = "unknown error"
        for attempt in range(MAX_ATTEMPTS):
            self.requests += 1
            try:
                response = self._client.get(SERPAPI_URL, params=query)
            except httpx.HTTPError as exc:
                last_error = f"http error: {type(exc).__name__}"
                if attempt + 1 < MAX_ATTEMPTS:
                    time.sleep(RETRY_BACKOFF)
                continue
            try:
                data = response.json()
            except ValueError:
                last_error = f"non-json response (status {response.status_code})"
                continue

            message: str | None = None
            if response.status_code != 200:
                message = data.get("error", "unknown") if isinstance(data, dict) else "unknown"
            elif data.get("error"):
                message = str(data["error"])
            if message is not None:
                if "Unsupported" in message and query.get("hl") != "en":
                    query["hl"] = "en"
                    last_error = f"hl fallback after: {message}"
                    continue
                return {"error": message}

            if data.get("search_metadata"):
                self.billable += 1
            return data
        return {"error": last_error}

    def close(self) -> None:
        self._client.close()


def count_jobs(raw: dict[str, Any]) -> int:
    return len(raw.get("jobs_results") or [])


def count_local(raw: dict[str, Any]) -> int:
    local = raw.get("local_results")
    if isinstance(local, list):
        return len(local)
    if isinstance(local, dict):
        return len(local.get("places") or [])
    return 0


def next_page_token(raw: dict[str, Any]) -> str | None:
    pagination = raw.get("serpapi_pagination") or {}
    return pagination.get("next_page_token")


def fetch_jobs(
    client: SerpApiClient, pair: dict[str, Any]
) -> tuple[list[dict[str, Any]], str | None]:
    """Return (pages, error)."""
    base = {
        "q": f"{pair['language']} {ROLE_TERMS}",
        "location": pair["location"],
        "gl": "in",
        "hl": pair["hl"],
    }
    page1 = client.get("google_jobs", base)
    if page1.get("error"):
        return [], str(page1["error"])

    pages = [page1]
    token = next_page_token(page1)
    if token:
        time.sleep(0.5)
        page2 = client.get("google_jobs", {**base, "next_page_token": token})
        if not page2.get("error"):
            pages.append(page2)
    return pages, None


def fetch_maps(client: SerpApiClient, pair: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return {query: raw_response} for each Maps query (errors included)."""
    results: dict[str, dict[str, Any]] = {}
    for query in MAPS_QUERIES:
        params = {
            "q": f"{query} {pair['language']}",
            "ll": f"@{pair['lat']},{pair['lng']},12z",
            "gl": "in",
            "hl": pair["hl"],
        }
        results[query] = client.get("google_maps", params)
        time.sleep(0.5)
    return results


def main() -> int:
    settings = get_settings()
    if not settings.serpapi_key:
        print("SERPAPI_KEY is not set (environment or .env). Add it and re-run.")
        return 1

    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    client = SerpApiClient(settings.serpapi_key)
    rows: list[dict[str, Any]] = []

    try:
        for pair in PAIRS:
            language = pair["language"]
            city = pair["city"]
            print(f"--- {language} / {city} (hl={pair['hl']}) ---")

            pages, jobs_error = fetch_jobs(client, pair)
            jobs_count = sum(count_jobs(page) for page in pages)
            (FIXTURES_DIR / f"search_{slug(language)}_{slug(city)}.json").write_text(
                json.dumps(
                    {
                        "engine": "google_jobs",
                        "hl_used": pair["hl"],
                        "hl_requested": pair["hl_requested"],
                        "pages": pages,
                    },
                    indent=2,
                )
            )

            maps = fetch_maps(client, pair)
            providers = sum(count_local(raw) for raw in maps.values())
            maps_errors = {
                slug(query): raw["error"] for query, raw in maps.items() if raw.get("error")
            }
            (FIXTURES_DIR / f"maps_{slug(city)}.json").write_text(
                json.dumps(
                    {
                        "engine": "google_maps",
                        "hl_used": pair["hl"],
                        "hl_requested": pair["hl_requested"],
                        "queries": {slug(query): raw for query, raw in maps.items()},
                    },
                    indent=2,
                )
            )

            rows.append(
                {
                    "language": language,
                    "city": city,
                    "hl_requested": pair["hl_requested"],
                    "hl_used": pair["hl"],
                    "jobs_pages": len(pages),
                    "jobs_count": jobs_count,
                    "providers": providers,
                    "jobs_error": jobs_error,
                    "maps_errors": maps_errors or None,
                }
            )
            print(f"    jobs={jobs_count} (pages={len(pages)}), providers={providers}")
            if jobs_error:
                print(f"    jobs error: {jobs_error}")
            for query, err in maps_errors.items():
                print(f"    maps[{query}] error: {err}")
    finally:
        client.close()

    print("\n=================== SPIKE REPORT ===================")
    header = f"{'language':<10} {'city':<11} {'hl':<4} {'jobs':>5} {'pages':>5} {'providers':>9}"
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{row['language']:<10} {row['city']:<11} {row['hl_used']:<4} "
            f"{row['jobs_count']:>5} {row['jobs_pages']:>5} {row['providers']:>9}"
        )

    jobs_ok = sum(1 for row in rows if row["jobs_count"] >= MIN_LISTINGS)
    providers_ok = sum(1 for row in rows if row["providers"] >= MIN_PROVIDERS)
    verdict = "GO" if jobs_ok >= 3 and providers_ok >= 3 else "NO-GO (revisit pairs)"

    print()
    print(f"Pairs with >= {MIN_LISTINGS} listings: {jobs_ok}/{len(rows)}")
    print(f"Pairs with >= {MIN_PROVIDERS} providers: {providers_ok}/{len(rows)}")
    print(f"HTTP requests (incl. retries): {client.requests}")
    print(f"Billable searches: {client.billable}")
    print(f"Verdict: {verdict}")

    (FIXTURES_DIR / "_spike_report.json").write_text(
        json.dumps(
            {
                "http_requests": client.requests,
                "billable_searches": client.billable,
                "listings_pairs_ok": jobs_ok,
                "providers_pairs_ok": providers_ok,
                "verdict": verdict,
                "rows": rows,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
