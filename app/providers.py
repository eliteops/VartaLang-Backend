# app/providers.py
"""Google Maps providers module (PRD v1.2, FR-2 / FR-12).

Pure functions: build the Maps query terms, parse raw SerpApi `google_maps`
results, filter by category/keywords, dedupe by place_id, keep the top 8.

Real `data/provider_filters.json` keys (all optional, owner: Dhawal):
    query_templates       : e.g. "translation services {language} {city}"
    include_categories    : Maps category names to keep
    exclude_categories    : Maps category names to drop
    include_name_keywords : words to match in the business name (keep)
    exclude_name_keywords : words to match in the business name (drop)
Filter rule (from data/README.md): keep a place if its category is in
``include_categories`` OR its name matches ``include_name_keywords``; drop
it if its category is in ``exclude_categories`` AND its name matches
nothing in ``include_name_keywords``; always drop names matching
``exclude_name_keywords``. Legacy ``query_terms`` / ``include_keywords`` /
``exclude_keywords`` keys are still accepted. Missing keys fall back to
the defaults below.
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


def _render(template: str, language: str, city: str) -> str:
    try:
        return template.format(language=language, city=city)
    except (KeyError, IndexError, ValueError):
        return f"{template} {language} {city}".strip()


def build_provider_queries(language: str, city: str, filters: dict | None = None) -> list[str]:
    """Server-built Maps queries: provider-type term + language + city (FR-2)."""
    filters = filters or {}
    templates = filters.get("query_templates")
    if isinstance(templates, (list, tuple)) and templates:
        rendered = [_render(str(t), language, city) for t in templates if str(t).strip()]
        return rendered[:MAX_QUERIES]
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


def _passes(
    provider: dict,
    include_cats: tuple[str, ...],
    exclude_cats: tuple[str, ...],
    include_names: tuple[str, ...],
    exclude_names: tuple[str, ...],
    include_any: tuple[str, ...],
    exclude_any: tuple[str, ...],
) -> bool:
    """Apply the data/README.md filter rule (category-aware)."""
    name = (provider.get("name") or "").casefold()
    category = (provider.get("category") or "").casefold()
    if any(x in name for x in exclude_names):
        return False
    if any(x in f"{name} {category}" for x in exclude_any):
        return False
    if category in exclude_cats and not any(i in name for i in include_names):
        return False
    if category in include_cats:
        return True
    if any(i in name for i in include_names):
        return True
    return any(i in f"{name} {category}" for i in include_any)


def select_providers(
    raw_results: list[dict],
    filters: dict | None = None,
    limit: int = MAX_PROVIDERS,
) -> list[dict]:
    """Parse, filter, dedupe by place_id, rank (rating, then reviews), cap."""
    filters = filters or {}
    include_cats = _list(filters, "include_categories", default=())
    exclude_cats = _list(filters, "exclude_categories", default=())
    include_names = _list(filters, "include_name_keywords", default=())
    exclude_names = _list(filters, "exclude_name_keywords", default=())
    include_any = _list(filters, "include_keywords", "keywords", "include", default=DEFAULT_INCLUDE)
    exclude_any = _list(
        filters, "exclude_keywords", "blocklist", "exclude", default=DEFAULT_EXCLUDE
    )

    seen: set[str] = set()
    kept: list[dict] = []
    for raw in raw_results:
        p = parse_provider(raw)
        if not p or p["place_id"] in seen:
            continue
        seen.add(p["place_id"])
        if _passes(
            p,
            include_cats,
            exclude_cats,
            include_names,
            exclude_names,
            include_any,
            exclude_any,
        ):
            kept.append(p)

    kept.sort(key=lambda p: (p["rating"] is None, -(p["rating"] or 0), -p["reviews"]))
    return kept[:limit]
