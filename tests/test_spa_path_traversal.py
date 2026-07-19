"""SPA fallback must never escape web_dist_dir (config#2631, CodeQL py/path-injection)."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

import api.main as main_module
from api.main import _safe_dist_path

client = TestClient(main_module.app)


def test_safe_dist_path_resolves_file_inside_dist(tmp_path):
    (tmp_path / "manifest.json").write_text("{}")

    assert _safe_dist_path(tmp_path, "manifest.json") == tmp_path / "manifest.json"


def test_safe_dist_path_rejects_dotdot_traversal(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (tmp_path / "secret.txt").write_text("nope")

    assert _safe_dist_path(dist, "../secret.txt") is None


def test_safe_dist_path_rejects_absolute_escape(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    outside = tmp_path / "outside"
    outside.write_text("nope")

    assert _safe_dist_path(dist, str(outside)) is None


def test_safe_dist_path_none_for_missing_file(tmp_path):
    assert _safe_dist_path(tmp_path, "does-not-exist.js") is None


def test_safe_dist_path_none_for_empty_path(tmp_path):
    assert _safe_dist_path(tmp_path, "") is None


def _rebuild_spa(monkeypatch, dist: str) -> None:
    monkeypatch.setattr(main_module, "settings", SimpleNamespace(web_dist_dir=dist))
    main_module._mount_spa()


def test_spa_fallback_serves_known_asset_end_to_end(monkeypatch, tmp_path):
    (tmp_path / "index.html").write_text("<html>spa</html>")
    (tmp_path / "manifest.json").write_text("{}")
    _rebuild_spa(monkeypatch, str(tmp_path))

    resp = client.get("/app/manifest.json")

    assert resp.status_code == 200
    assert resp.text == "{}"


def test_spa_fallback_falls_back_to_index_for_client_route(monkeypatch, tmp_path):
    (tmp_path / "index.html").write_text("<html>spa</html>")
    _rebuild_spa(monkeypatch, str(tmp_path))

    resp = client.get("/app/workouts/42")

    assert resp.status_code == 200
    assert resp.text == "<html>spa</html>"


def test_spa_fallback_blocks_encoded_traversal_end_to_end(monkeypatch, tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>spa</html>")
    (tmp_path / "secret.txt").write_text("outside-dist-should-never-be-served")
    _rebuild_spa(monkeypatch, str(dist))

    # %2e%2e survives the test client's own URL normalization (a bare "../"
    # gets collapsed client-side before the request is even sent) — this is
    # the shape that actually reaches spa_fallback with ".." intact.
    resp = client.get("/app/%2e%2e/secret.txt")

    assert resp.status_code == 200
    assert resp.text == "<html>spa</html>"
