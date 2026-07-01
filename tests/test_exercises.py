"""Exercise search, dedup, alias, and history endpoint tests."""

from __future__ import annotations

from unittest import mock

import numpy as np
import pytest


def test_search_keyword_acronym(client):
    # Curated alias RDL -> Romanian Deadlift, resolved via BM25.
    r = client.get("/api/exercises/search", params={"q": "RDL", "limit": 5})
    assert r.status_code == 200
    names = [h["exercise"]["name"] for h in r.json()]
    assert "Romanian Deadlift" in names


def test_search_semantic_description(client):
    # No "bench press" tokens by name only -> needs the dense retriever.
    r = client.get(
        "/api/exercises/search",
        params={"q": "chest exercise lying on a bench pressing a barbell", "limit": 5},
    )
    names = [h["exercise"]["name"].lower() for h in r.json()]
    assert any("bench press" in n for n in names)


def test_create_exact_duplicate_blocked(client):
    r = client.post("/api/exercises", json={"name": "Barbell Deadlift"})
    assert r.status_code == 200
    body = r.json()
    assert body["created"] is False
    assert body["reason"] == "exact"
    assert body["duplicate_of"]["name"] == "Barbell Deadlift"


def test_create_novel_multiword_exercise_not_blocked(client):
    # A novel name with only loosely-similar catalog entries must save on the
    # spot (no false-positive "did you mean?" block). Regression for the
    # "lunge dumbbell overhead" case.
    r = client.post("/api/exercises", json={"name": "lunge dumbbell overhead"})
    assert r.status_code == 200
    body = r.json()
    assert body["created"] is True, body
    assert body["reason"] == "created"
    new_id = body["exercise"]["id"]

    # and it persists / is findable
    hits = client.get("/api/exercises/search", params={"q": "lunge dumbbell overhead"}).json()
    assert new_id in [h["exercise"]["id"] for h in hits]


def test_create_with_similar_hint_never_blocks(client):
    # A near-duplicate name must still create on the spot (never gated) and
    # surface the match as a non-blocking hint alongside the new exercise.
    from api.services.search import get_search_service

    svc = get_search_service()
    existing = client.get(
        "/api/exercises/search", params={"q": "Barbell Deadlift"}
    ).json()[0]["exercise"]

    # Force a deterministic hint: pin the existing exercise's name-only vector
    # to unit-x and the candidate embedding to the same direction, independent
    # of the real embedding model's behavior on this particular string pair.
    v = np.zeros(svc.settings.embed_dim, dtype=np.float32)
    v[0] = 1.0
    svc.name_vec.set(str(existing["id"]), v)
    try:
        with mock.patch("api.services.search.embed", return_value=v * 0.95):
            r = client.post("/api/exercises", json={"name": "Barbell Deadlift Variant XYZ"})
    finally:
        svc.name_vec.delete(str(existing["id"]))
        svc.name_vec.save()

    assert r.status_code == 200
    body = r.json()
    assert body["created"] is True
    assert body["reason"] == "created"
    assert body["similar_to"]["id"] == existing["id"]
    assert body["similar_to_similarity"] == pytest.approx(1.0)


def test_find_similar_hint_respects_threshold(client):
    from api.services.search import get_search_service

    svc = get_search_service()
    v = np.zeros(svc.settings.embed_dim, dtype=np.float32)
    v[0] = 1.0
    svc.name_vec.set("999999", v)
    try:
        with mock.patch("api.services.search.embed", return_value=v * 0.95):
            hit = svc.find_similar_hint("close variant")
        assert hit == (999999, pytest.approx(1.0))

        orthogonal = np.zeros(svc.settings.embed_dim, dtype=np.float32)
        orthogonal[1] = 1.0
        with mock.patch("api.services.search.embed", return_value=orthogonal):
            assert svc.find_similar_hint("unrelated exercise") is None
    finally:
        svc.name_vec.delete("999999")
        svc.name_vec.save()


def test_create_new_exercise_then_searchable(client):
    r = client.post(
        "/api/exercises",
        json={"name": "Cossack Goblet Squat", "primary_muscles": ["quadriceps"], "force": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["created"] is True
    new_id = body["exercise"]["id"]
    assert body["exercise"]["provenance"] == "user"

    # Newly created exercise is immediately findable (FTS + vector indexed).
    r2 = client.get("/api/exercises/search", params={"q": "Cossack Goblet Squat"})
    ids = [h["exercise"]["id"] for h in r2.json()]
    assert new_id in ids


def test_alias_makes_exercise_findable(client):
    # Add a custom abbreviation to a canonical exercise, then find it by that alias.
    found = client.get("/api/exercises/search", params={"q": "Glute Ham Raise"}).json()
    ex_id = found[0]["exercise"]["id"]

    r = client.post(f"/api/exercises/{ex_id}/aliases", json={"alias_text": "GHR razor"})
    assert r.status_code == 200
    assert "GHR razor" in r.json()["aliases"]

    hit = client.get("/api/exercises/search", params={"q": "GHR razor"}).json()
    assert hit and hit[0]["exercise"]["id"] == ex_id


def test_get_exercise_404(client):
    assert client.get("/api/exercises/99999999").status_code == 404
