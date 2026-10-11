"""Tests for the coverage endpoint (FR-13)."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_coverage_serves_grid_for_snapshot_or_zeroed() -> None:
    r = client.get("/api/coverage")
    assert r.status_code == 200
    body = r.json()
    assert len(body["rows"]) == 8 * 5
    assert body["method_note"]
    for row in body["rows"]:
        assert row["language"] and row["city"]
        assert row["explicit_count"] >= 0
        assert row["inferred_count"] >= 0


def test_coverage_rows_match_snapshot_file_when_present() -> None:
    import json

    from app.api.coverage import SNAPSHOT_FILE

    if not SNAPSHOT_FILE.exists():
        return
    snap = json.loads(SNAPSHOT_FILE.read_text(encoding="utf-8"))
    expected = {(row["language"], row["city"]): row for row in snap["rows"]}
    body = client.get("/api/coverage").json()
    for row in body["rows"]:
        key = (row["language"], row["city"])
        if key in expected:
            assert row["explicit_count"] == int(expected[key]["explicit_count"] or 0)
            assert row["inferred_count"] == int(expected[key]["inferred_count"] or 0)
