"""Tests for search orchestration (PRD FR-3..FR-8, FR-11, FR-15)."""

from __future__ import annotations

from app.config import Settings
from app.services import search as svc


def _job(**kw) -> dict:
    base = {
        "title": "Tamil Translator",
        "company_name": "Acme",
        "location": "Chennai, Tamil Nadu",
        "description": "Translate documents. In-hand salary of ₹10000 - ₹16000 per month.",
        "apply_options": [{"title": "Acme", "link": "https://acme.example/apply/1"}],
        "extensions": ["3 days ago"],
        "via": "LinkedIn",
    }
    base.update(kw)
    return base


def test_assemble_scores_dedupes_filters_and_parses_salary() -> None:
    jobs = [
        _job(),
        _job(),  # duplicate apply link
        _job(extensions=["45 days ago"]),  # FR-8 freshness
        _job(apply_options=[]),  # FR-5: no apply link
        _job(title="Delivery Executive", description="Deliver packages across Chennai."),
    ]
    payload = svc._assemble("tamil", "Tamil", "Chennai", jobs, [], 200, "live")
    assert payload["meta"]["source"] == "live"
    assert len(payload["listings"]) == 1
    listing = payload["listings"][0]
    assert listing["relevance_label"] == "Explicit match"
    assert listing["salary_text"] == "₹10000 - ₹16000"
    assert listing["matched_terms"]
    assert listing["apply_link"] == "https://acme.example/apply/1"
    assert payload["meta"]["visibility"] == {"explicit": 1, "inferred": 0}


def test_demo_mode_serves_seeded_fixture(monkeypatch) -> None:
    monkeypatch.setattr(svc, "get_settings", lambda: Settings(demo_mode=True, serpapi_key=None))
    monkeypatch.setattr(svc.repo, "budget_remaining", lambda cap: cap)
    doc = svc.run_search("Tamil", "Chennai")
    assert doc is not None
    assert doc["meta"]["source"] == "fallback"
    assert doc["listings"]
    assert doc["notice"]


def test_budget_exhausted_never_calls_upstream(monkeypatch) -> None:
    monkeypatch.setattr(svc, "get_settings", lambda: Settings(demo_mode=False, serpapi_key="key"))
    monkeypatch.setattr(svc.repo, "budget_remaining", lambda cap: 0)
    monkeypatch.setattr(svc.repo, "find_cached_run", lambda lang, loc: None)

    def _boom(*args, **kwargs):
        raise AssertionError("upstream call attempted with an exhausted budget")

    monkeypatch.setattr(svc, "_live", _boom)
    doc = svc.run_search("Tamil", "Chennai")
    assert doc is not None
    assert doc["meta"]["daily_budget_remaining"] == 0


def test_cache_hit_returns_stored_payload(monkeypatch) -> None:
    cached = {
        "fetched_at": "2026-10-11T10:00:00+00:00",
        "explicit": 2,
        "inferred": 1,
        "listings": [
            {
                "title": "Stored Tamil job",
                "apply_link": "https://acme.example/apply/9",
                "relevance_label": "Explicit match",
                "relevance_score": 5.0,
                "matched_terms": ["Tamil"],
                "trust_hints": [],
            }
        ],
        "providers": [{"name": "Acme Translations", "category": "Translation service"}],
    }
    monkeypatch.setattr(svc, "get_settings", lambda: Settings(demo_mode=False, serpapi_key="key"))
    monkeypatch.setattr(svc.repo, "budget_remaining", lambda cap: 137)
    monkeypatch.setattr(svc.repo, "find_cached_run", lambda lang, loc: cached)
    doc = svc.run_search("Tamil", "Chennai")
    assert doc is not None
    assert doc["meta"]["source"] == "cache"
    assert doc["meta"]["daily_budget_remaining"] == 137
    assert doc["meta"]["visibility"] == {"explicit": 2, "inferred": 1}
    assert doc["listings"][0]["title"] == "Stored Tamil job"
    assert doc["providers_label"].endswith("Chennai. Confirm language availability directly.")


def test_invalid_language_is_rejected() -> None:
    assert svc.run_search("Klingon", "Chennai") is None
