"""Golden checks for the five demo pairs (PRD section 16, DoD #1) and the
native-script provider filter fix.

DoD #1: each rehearsed pair must show at least 5 relevant listings, or an
honest low-visibility view plus at least 5 plausible providers. These run in
demo mode against the sealed fixtures, so they need no API key and make no
upstream calls.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.core.providers import load_filters, select_providers
from app.main import app
from app.services import search as svc

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"

DEMO_PAIRS = [
    ("Hindi", "Delhi NCR", "hindi", "delhi-ncr"),
    ("Hindi", "Lucknow", "hindi", "lucknow"),
    ("Tamil", "Chennai", "tamil", "chennai"),
    ("Bengali", "Kolkata", "bengali", "kolkata"),
    ("Maithili", "Patna", "maithili", "patna"),
]

client = TestClient(app)


@pytest.fixture()
def demo_settings(monkeypatch):
    monkeypatch.setattr(svc, "get_settings", lambda: Settings(demo_mode=True, serpapi_key=None))
    monkeypatch.setattr(svc.repo, "budget_remaining", lambda cap: cap)


@pytest.mark.parametrize(("language", "location"), [(a, b) for a, b, _, _ in DEMO_PAIRS])
def test_demo_pair_meets_definition_of_done(demo_settings, language: str, location: str) -> None:
    r = client.post("/api/search", json={"language": language, "location": location})
    assert r.status_code == 200
    body = r.json()
    listings = body["listings"]
    providers = body["providers"]
    assert len(listings) >= 5 or len(providers) >= 5, (
        f"{language}/{location}: {len(listings)} listings, {len(providers)} providers"
    )
    assert body["notice"]
    assert body["providers_label"]


@pytest.mark.parametrize(("_lang", "_city", "lang_id", "city_id"), DEMO_PAIRS)
def test_sealed_fixture_exists(_lang, _city, lang_id, city_id) -> None:
    assert (FIXTURES / f"search_{lang_id}_{city_id}.json").exists()


def test_devanagari_category_places_survive_the_filter() -> None:
    """Hindi-locale Maps responses carry Devanagari `type` and no `type_id`."""
    filters = load_filters(ROOT / "data" / "provider_filters.json")
    raw = [
        {
            "title": "रॉयल ट्रांसलेशन & सर्विसेज",
            "place_id": "ChIJtest1",
            "type": "अनुवादक",
            "type_id": None,
            "types": ["अनुवादक", "इंटरनेट कैफ़े"],
            "rating": 5.0,
            "reviews": 12,
        },
        {
            "title": "Spoken English Coaching Classes",
            "place_id": "ChIJtest2",
            "type": "Language school",
            "rating": 4.9,
            "reviews": 99,
        },
    ]
    kept = select_providers(raw, filters)
    assert [p["name"] for p in kept] == ["रॉयल ट्रांसलेशन & सर्विसेज"]


def test_sealed_fixtures_have_contract_shape() -> None:
    for _lang, _city, lang_id, city_id in DEMO_PAIRS:
        path = FIXTURES / f"search_{lang_id}_{city_id}.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        assert set(doc) >= {"meta", "listings", "providers", "notice"}
        assert doc["meta"]["source"] in {"cache", "live", "fallback"}
