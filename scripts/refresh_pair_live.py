"""Refresh one demo pair with a live SerpApi run and reseal its fixture.

The spike found no Google Jobs results for Bhojpuri/Lucknow and thin Maps for
Patna, so DoD #1 was unmet for those pairs. This re-runs them through the
production path (`run_search`: cache -> budget -> live Jobs page 2 -> live
Maps -> score/dedupe -> store) and writes the payload to the sealed fixture.

Costs are bounded by the daily cap (FR-7) and the 2-page Jobs limit (FR-3).

Usage:  uv run python scripts/refresh_pair_live.py bhojpuri "Lucknow"
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.services.search import run_search  # noqa: E402

FIXTURES = REPO_ROOT / "fixtures"


def main() -> None:
    language, location = sys.argv[1], sys.argv[2]
    payload = run_search(language, location)
    if payload is None:
        print(f"{language}/{location}: rejected by validation")
        raise SystemExit(1)
    listings = payload.get("listings") or []
    providers = payload.get("providers") or []
    meta = payload.get("meta") or {}
    print(
        f"{language}/{location}: source={meta.get('source')} "
        f"listings={len(listings)} providers={len(providers)} "
        f"visibility={meta.get('visibility')} budget_left={meta.get('daily_budget_remaining')}"
    )
    if not listings and not providers:
        print("  live run returned nothing; fixture left unchanged")
        return
    from app.core.data_loader import resolve_city, resolve_language

    lang_id = str((resolve_language(language) or {}).get("id", language)).lower()
    city = resolve_city(location) or {}
    city_id = str(city.get("id") or location.strip().lower().replace(" ", "-"))
    payload["resealed_at"] = datetime.now(UTC).isoformat()
    out = FIXTURES / f"search_{lang_id}_{city_id}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  wrote {out.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
