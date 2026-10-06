"""Loaders for the Dhawal-owned `data/` files (PRD v1.2, FR-1/FR-2/FR-12/FR-13).

Pure file I/O + lookup helpers. Results are cached per process with
`functools.lru_cache` (files change via PR, not at runtime).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

METHOD_NOTE = (
    "One lens (Google Jobs), snapshot date, query-dependent. "
    "Low visibility does not prove low demand."
)

TRUST_NOTICE = (
    "Results come from public sources. VartaLang does not verify employers "
    "or providers. Never pay to apply."
)


def _read_json(filename: str) -> dict:
    path = DATA_DIR / filename
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{filename} must contain a JSON object")
    return data


@lru_cache(maxsize=1)
def get_languages_doc() -> dict:
    """Full `languages.json` document (allowlist is the source of truth)."""
    return _read_json("languages.json")


@lru_cache(maxsize=1)
def get_cities_doc() -> dict:
    """Full `cities.json` document."""
    return _read_json("cities.json")


def list_languages() -> list[dict]:
    """Allowlist entries: {id, name, native_name}."""
    return [
        {"id": lang["id"], "name": lang["name"], "native_name": lang["native_name"]}
        for lang in get_languages_doc().get("languages", [])
    ]


def language_ids() -> set[str]:
    return {lang["id"] for lang in get_languages_doc().get("languages", [])}


def resolve_language(value: str) -> dict | None:
    """Match a language by id or English name (case-insensitive)."""
    want = value.strip().casefold()
    for lang in get_languages_doc().get("languages", []):
        if want in (str(lang.get("id", "")).casefold(), str(lang.get("name", "")).casefold()):
            return lang
    return None


def resolve_city(value: str) -> dict | None:
    """Match a city by id, display name or alias (case-insensitive)."""
    want = value.strip().casefold()
    for city in get_cities_doc().get("cities", []):
        candidates = [city.get("id", ""), city.get("display_name", "")]
        candidates.extend(city.get("aliases", []) or [])
        if any(want == str(c).strip().casefold() for c in candidates if c):
            return city
    return None


def normalize_location(value: str) -> str:
    """Collapse whitespace; resolve to the canonical display name when known."""
    cleaned = " ".join(value.strip().split())
    city = resolve_city(cleaned)
    if city:
        return str(city.get("display_name", cleaned))
    return cleaned


def snapshot_grid() -> tuple[list[str], list[str]]:
    """The (languages, cities) grid for the visibility snapshot (FR-13)."""
    snap = get_languages_doc().get("snapshot", {}) or {}
    return list(snap.get("languages", [])), list(snap.get("cities", []))
