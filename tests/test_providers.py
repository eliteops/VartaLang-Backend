# tests/test_providers.py
from app.providers import (
    build_provider_queries,
    parse_provider,
    safe_url,
    select_providers,
)


def raw(
    pid, title, type_="Translation service", rating=4.0, reviews=10, website="https://example.com"
):
    return {
        "place_id": pid,
        "title": title,
        "type": type_,
        "rating": rating,
        "reviews": reviews,
        "website": website,
        "address": "Chennai",
        "gps_coordinates": {"latitude": 13.0, "longitude": 80.2},
    }


def test_queries_include_language_and_city():
    qs = build_provider_queries("Tamil", "Chennai")
    assert qs == ["translation services Tamil Chennai", "transcription services Tamil Chennai"]


def test_queries_use_filter_terms_and_cap_at_two():
    qs = build_provider_queries("Tamil", "Chennai", {"query_terms": ["a", "b", "c"]})
    assert len(qs) == 2


def test_dedupe_by_place_id():
    out = select_providers([raw("1", "A Translators"), raw("1", "A Translators again")])
    assert len(out) == 1


def test_filters_out_irrelevant_and_excluded():
    items = [
        raw("1", "Good Translators"),
        raw("2", "Pizza Place", type_="Restaurant"),
        raw("3", "Tamil Coaching Classes", type_="Translation service"),
    ]
    assert [p["place_id"] for p in select_providers(items)] == ["1"]


def test_caps_at_eight_and_ranks_by_rating():
    items = [raw(str(i), f"T{i} Translators", rating=3 + i / 10) for i in range(12)]
    out = select_providers(items)
    assert len(out) == 8
    assert out[0]["rating"] >= out[-1]["rating"]


def test_unrated_goes_last():
    out = select_providers(
        [raw("1", "X Translators", rating=None), raw("2", "Y Translators", rating=3.0)]
    )
    assert [p["place_id"] for p in out] == ["2", "1"]


def test_only_http_links():
    assert safe_url("javascript:alert(1)") is None
    assert safe_url("ftp://x.com") is None
    assert safe_url("https://x.com") == "https://x.com"
    assert parse_provider(raw("1", "X", website="javascript:alert(1)"))["website"] is None


def test_html_stripped_from_name():
    assert parse_provider(raw("1", "<b>Acme</b> Translators"))["name"] == "Acme Translators"


def test_missing_name_or_id_rejected():
    assert parse_provider({"title": "No id"}) is None
    assert parse_provider({"place_id": "1"}) is None
