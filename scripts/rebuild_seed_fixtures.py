"""Rebuild the sealed demo fixtures so each pair carries its Maps providers.

The seeded `fixtures/search_*.json` payloads were captured before the
providers module existed, so DoD #1's "≥5 plausible providers" bar could not
be met offline. This script re-derives providers from the saved Maps
fixtures through the real `select_providers` filter and rewrites meta
(visibility recomputed from the listings actually served, FR-13/FR-16).

Usage:  uv run python scripts/rebuild_seed_fixtures.py [lang city ...]
With no arguments it rebuilds every pair that has a Maps fixture.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.core.data_loader import TRUST_NOTICE, resolve_city, resolve_language  # noqa: E402
from app.core.providers import PROVIDERS_LABEL, load_filters, select_providers  # noqa: E402

FIXTURES = REPO_ROOT / "fixtures"
MAPS_KEY_FIX = {"delhi-ncr": "delhi_ncr"}

PAIRS = [
    ("hindi", "delhi-ncr"),
    ("tamil", "chennai"),
    ("bengali", "kolkata"),
    ("maithili", "patna"),
    ("bhojpuri", "lucknow"),
]


def maps_places(city_id: str) -> list[dict]:
    path = FIXTURES / f"maps_{MAPS_KEY_FIX.get(city_id, city_id)}.json"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        return []
    places: list[dict] = []
    for qdoc in (doc.get("queries") or {}).values():
        places.extend(qdoc.get("local_results") or [])
    return places


def rebuild(lang_id: str, city_id: str) -> bool:
    seeded_path = FIXTURES / f"search_{lang_id}_{city_id}.json"
    if not seeded_path.exists():
        return False
    doc = json.loads(seeded_path.read_text(encoding="utf-8"))
    lang = resolve_language(lang_id)
    city = resolve_city(city_id)
    city_disp = str(city.get("display_name")) if city else city_id
    filt = load_filters(REPO_ROOT / "data" / "provider_filters.json")
    kept = select_providers(maps_places(city_id), filt)[:8]
    providers = [
        {
            "name": p.get("name") or "",
            "category": p.get("category"),
            "address": p.get("address"),
            "rating": p.get("rating"),
            "website": p.get("website"),
            "phone": p.get("phone"),
        }
        for p in kept
    ]
    listings = doc.get("listings") or []
    vis = {"explicit": 0, "inferred": 0}
    for item in listings:
        vis["explicit" if item.get("relevance_label") == "Explicit match" else "inferred"] += 1
    doc["meta"] = {
        "source": "fallback",
        "fetched_at": datetime.now(UTC).isoformat(),
        "daily_budget_remaining": 0,
        "visibility": vis,
    }
    doc["listings"] = listings
    doc["providers"] = providers
    doc["providers_label"] = PROVIDERS_LABEL.format(city=city_disp)
    doc["notice"] = TRUST_NOTICE
    seeded_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"{lang_id}/{city_id}: listings={len(listings)} providers={len(providers)} "
        f"vis={vis} lang={lang.get('name') if lang else '?'}"
    )
    return True


def main() -> None:
    args = sys.argv[1:]
    pairs = list(zip(args[0::2], args[1::2], strict=True)) if args else PAIRS
    for lang_id, city_id in pairs:
        if not rebuild(lang_id, city_id):
            print(f"{lang_id}/{city_id}: no sealed fixture, skipped")


if __name__ == "__main__":
    main()
