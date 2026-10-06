"""Temporary diagnostic: measure google_jobs latency + OR-syntax behavior.

Run:  uv run python -m scripts.diag_jobs
"""

import time

from app.config import get_settings
from scripts.spike_serpapi import SerpApiClient

CASES = [
    (
        "Tamil OR-terms",
        {
            "q": "Tamil translator OR interpreter OR transcription",
            "location": "Chennai, India",
            "gl": "in",
            "hl": "ta",
        },
    ),
    (
        "Tamil simple",
        {"q": "Tamil translator", "location": "Chennai, India", "gl": "in", "hl": "ta"},
    ),
    (
        "Bengali OR-terms",
        {
            "q": "Bengali translator OR interpreter OR transcription",
            "location": "Kolkata, India",
            "gl": "in",
            "hl": "bn",
        },
    ),
]


def main() -> None:
    client = SerpApiClient(get_settings().serpapi_key, timeout=180.0)
    try:
        for name, params in CASES:
            start = time.time()
            result = client.get("google_jobs", params)
            elapsed = time.time() - start
            count = len(result.get("jobs_results") or [])
            print(f"{name}: elapsed={elapsed:.1f}s error={result.get('error')} count={count}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
