"""Tests for the coverage endpoint (FR-13)."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_coverage_falls_back_to_zeroed_grid() -> None:
    r = client.get("/api/coverage")
    assert r.status_code == 200
    body = r.json()
    assert len(body["rows"]) == 8 * 5
    assert all(row["explicit_count"] == 0 for row in body["rows"])
