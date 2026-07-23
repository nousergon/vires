"""SPA fallback must never escape web_dist_dir (config#2631, CodeQL py/path-injection).

The fix uses a mount-time whitelist approach (not a per-request containment
check): _safe_dist_path was replaced by _fallback_files dict populated at
mount time. Unit tests for _safe_dist_path are removed; the end-to-end tests
below exercise the whitelist behavior at the HTTP layer.
"""

from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

import api.main as main_module

client = TestClient(main_module.app)


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
