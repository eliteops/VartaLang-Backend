# app/providers.py
"""Google Maps providers module (PRD v1.2, FR-2 / FR-12).

Pure functions: build the Maps query terms, parse raw SerpApi `google_maps`
results, filter by category/keywords, dedupe by place_id, keep the top 8.

provider_filters.json is read tolerantly. Recognised keys (all optional):
    query_terms      : provider-type terms used to build Maps queries
    include_keywords : keep a place if name/category contains any of these
    exclude_keywords : drop a place if name/category contains any of these
Missing keys fall back to the defaults below.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

MAX_PROVIDERS = 8
MAX_QUERIES = 2

DEFAULT_QUERY_TERMS = ("translation services", "transcription services")
DEFAULT_INCLUDE = (
    "translat",
    "transcri",
    "locali",
    "interpret",
    "multilingual",
    "language service",
    "voice over",
    "dubbing",
    "subtitl",
)
DEFAULT_EXCLUDE = ("coaching", "classes", "tuition", "school", "academy")

PROVIDERS_LABEL = "Providers in {city}. Confirm language availability directly."


def load_filters(path: str | Path = "data/provider_filters.json") -> dict:
    with Path(path).open(encoding="utf-8") as fh:
        return json.load(fh)


def _list(filters: dict, *keys: str, default: tuple[str, ...]) -> tuple[str, ...]:
    for key in keys:
        val = filters.get(key)
        if isinstance(val, (list, tuple)) and val:
            return tuple(str(v).casefold() for v in val)
    return tuple(v.casefold() for v in default)


def build_provider_queries(language: str, city: str, filters: dict | None = None) -> list[str]:
    """Server-built Maps queries: provider-type term + language + city (FR-2)."""
    filters = filters or {}
    terms = _list(filters, "query_terms", "search_terms", default=DEFAULT_QUERY_TERMS)
    return [f"{t} {language} {city}" for t in terms[:MAX_QUERIES]]


def safe_url(url: str | None) -> str | None:
    """Only http/https links are ever shown (FR-10)."""
    if not url or not isinstance(url, str):
        return None
    parsed = urlparse(url.strip())
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return url.strip()
    return None


def _clean(text: str | None) -> str | None:
    if text is None:
        return None
    text = re.sub(r"<[^>]*>", "", str(text))  # strip HTML
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def parse_provider(raw: dict) -> dict | None:
    """Map one raw SerpApi google_maps item to our provider shape."""
    name = _clean(raw.get("title") or raw.get("name"))
    place_id = raw.get("place_id") or raw.get("data_id")
    if not name or not place_id:
        return None
    types = raw.get("types")
    category = raw.get("type") or (types[0] if isinstance(types, list) and types else None)
    gps = raw.get("gps_coordinates") or {}
    rating = raw.get("rating")
    return {
        "place_id": str(place_id),
        "name": name,
        "category": _clean(category),
        "address": _clean(raw.get("address")),
        "rating": float(rating) if isinstance(rating, (int, float)) else None,
        "reviews": raw.get("reviews") if isinstance(raw.get("reviews"), int) else 0,
        "website": safe_url(raw.get("website")),
        "phone": _clean(raw.get("phone")),
        "lat": gps.get("latitude"),
        "lng": gps.get("longitude"),
    }


def _passes(provider: dict, include: tuple[str, ...], exclude: tuple[str, ...]) -> bool:
    text = f"{provider['name']} {provider.get('category') or ''}".casefold()
    if any(x in text for x in exclude):
        return False
    return any(i in text for i in include)


def select_providers(
    raw_results: list[dict],
    filters: dict | None = None,
    limit: int = MAX_PROVIDERS,
) -> list[dict]:
    """Parse, filter, dedupe by place_id, rank (rating, then reviews), cap."""
    filters = filters or {}
    include = _list(filters, "include_keywords", "keywords", "include", default=DEFAULT_INCLUDE)
    exclude = _list(filters, "exclude_keywords", "blocklist", "exclude", default=DEFAULT_EXCLUDE)

    seen: set[str] = set()
    kept: list[dict] = []
    for raw in raw_results:
        p = parse_provider(raw)
        if not p or p["place_id"] in seen:
            continue
        seen.add(p["place_id"])
        if _passes(p, include, exclude):
            kept.append(p)

    kept.sort(key=lambda p: (p["rating"] is None, -(p["rating"] or 0), -p["reviews"]))
    return kept[:limit]
