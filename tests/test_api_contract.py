"""Contract tests for the Oct-4 API core (PRD section 10, FR-1/FR-9/FR-13)."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_languages_returns_allowlist() -> None:
    r = client.get("/api/languages")
    assert r.status_code == 200
    body = r.json()
    ids = [x["id"] for x in body["languages"]]
    assert {"hindi", "tamil", "bengali", "maithili", "bhojpuri"} <= set(ids)


def test_search_ok_returns_contract_shape() -> None:
    r = client.post("/api/search", json={"language": "Tamil", "location": "Chennai"})
    assert r.status_code == 200
    body = r.json()
    assert {"meta", "listings", "providers", "notice"} <= set(body)
    assert body["meta"]["source"] in ("cache", "live", "fallback")
    assert "does not verify" in body["notice"]


def test_search_rejects_unknown_language() -> None:
    r = client.post("/api/search", json={"language": "Klingon", "location": "Chennai"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_input"


def test_search_rejects_bad_location_and_pin() -> None:
    bad_short = {"language": "Tamil", "location": "A"}
    assert client.post("/api/search", json=bad_short).status_code == 422
    bad_chars = {"language": "Tamil", "location": "Chennai!!"}
    assert client.post("/api/search", json=bad_chars).status_code == 422
    bad_pin = {"language": "Tamil", "location": "Chennai", "pin_code": "123"}
    assert client.post("/api/search", json=bad_pin).status_code == 422


def test_coverage_returns_grid_and_note() -> None:
    r = client.get("/api/coverage")
    assert r.status_code == 200
    body = r.json()
    assert len(body["rows"]) == 8 * 5
    assert "Low visibility does not prove low demand" in body["method_note"]
