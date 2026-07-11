"""The /version endpoint — the SW-independent staleness signal (vires-ops#59)."""

from __future__ import annotations

import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from api.main import app
from api.routers import version as version_module

client = TestClient(app)


def _point_dist_at(monkeypatch, path: str) -> None:
    """Make read_build_id() resolve its version.json under ``path``."""
    monkeypatch.setattr(
        version_module,
        "get_settings",
        lambda: SimpleNamespace(web_dist_dir=path),
    )


def test_version_reports_deployed_build_id(monkeypatch, tmp_path):
    (tmp_path / "version.json").write_text(json.dumps({"buildId": "abc1234"}))
    _point_dist_at(monkeypatch, str(tmp_path))

    resp = client.get("/version")

    assert resp.status_code == 200
    assert resp.json() == {"buildId": "abc1234"}
    # Must never be cached — the whole point is SW/HTTP-cache independence.
    assert "no-store" in resp.headers["cache-control"]


def test_version_unknown_when_no_bundle(monkeypatch, tmp_path):
    # No version.json written -> graceful "unknown", not a 500.
    _point_dist_at(monkeypatch, str(tmp_path))

    resp = client.get("/version")

    assert resp.status_code == 200
    assert resp.json() == {"buildId": "unknown"}


def test_version_unknown_on_garbled_file(monkeypatch, tmp_path):
    (tmp_path / "version.json").write_text("not json{")
    _point_dist_at(monkeypatch, str(tmp_path))

    assert client.get("/version").json() == {"buildId": "unknown"}


def test_version_unknown_on_missing_key(monkeypatch, tmp_path):
    (tmp_path / "version.json").write_text(json.dumps({"other": "x"}))
    _point_dist_at(monkeypatch, str(tmp_path))

    assert client.get("/version").json() == {"buildId": "unknown"}


def test_version_route_wins_over_spa_fallback():
    # /version is a real route, not the SPA catch-all: JSON, not index.html.
    resp = client.get("/version")
    assert resp.headers["content-type"].startswith("application/json")
    assert set(resp.json().keys()) == {"buildId"}
