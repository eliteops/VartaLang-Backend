"""Integration: loaders read the real Dhawal-owned `data/` files."""

from pathlib import Path

from app.providers import build_provider_queries, load_filters, select_providers
from app.scoring import load_keywords, score_listing

DATA = Path(__file__).resolve().parent.parent / "data"


def test_real_tamil_keywords_include_native_script() -> None:
    kw = load_keywords("tamil", data_dir=DATA / "keywords")
    assert "\u0ba4\u0bae\u0bbf\u0bb4\u0bcd" in kw.names
    s = score_listing(
        {
            "title": "\u0ba4\u0bae\u0bbf\u0bb4\u0bcd Translator",
            "location": "Chennai",
            "snippet": "",
            "posted_days_ago": 2,
        },
        kw,
        "Chennai",
    )
    assert s is not None and s.label == "Explicit match"


def test_real_maithili_loads_hindi_adjacency() -> None:
    kw = load_keywords("maithili", data_dir=DATA / "keywords")
    assert "hindi" in {a.casefold() for a in kw.adjacent}
    assert "Hindi" in kw.adjacent


def test_real_provider_filters_build_queries_and_filter() -> None:
    filters = load_filters(DATA / "provider_filters.json")
    qs = build_provider_queries("Tamil", "Chennai", filters)
    assert qs[0] == "translation services Tamil Chennai"
    good = {
        "place_id": "1",
        "title": "Acme Translation Services",
        "type": "Translation service",
        "rating": 4.5,
        "reviews": 5,
    }
    school = {
        "place_id": "2",
        "title": "Acme Language School",
        "type": "Language school",
        "rating": 4.9,
        "reviews": 50,
    }
    coached = {
        "place_id": "3",
        "title": "IELTS Coaching Hub",
        "type": "Translation service",
        "rating": 4.9,
        "reviews": 50,
    }
    out = select_providers([good, school, coached], filters)
    assert [p["place_id"] for p in out] == ["1"]
