"""Exercise search, dedup, alias, and history endpoint tests."""

from __future__ import annotations

from unittest import mock

import numpy as np
import pytest


def test_search_keyword_acronym(client):
    # Curated alias RDL -> Romanian Deadlift, resolved via BM25.
    r = client.get("/app/api/exercises/search", params={"q": "RDL", "limit": 5})
    assert r.status_code == 200
    names = [h["exercise"]["name"] for h in r.json()]
    assert "Romanian Deadlift" in names


def test_search_semantic_description(client):
    # No "bench press" tokens by name only -> needs the dense retriever.
    r = client.get(
        "/app/api/exercises/search",
        params={"q": "chest exercise lying on a bench pressing a barbell", "limit": 5},
    )
    names = [h["exercise"]["name"].lower() for h in r.json()]
    assert any("bench press" in n for n in names)


def test_create_exact_duplicate_blocked(client):
    r = client.post("/app/api/exercises", json={"name": "Barbell Deadlift"})
    assert r.status_code == 200
    body = r.json()
    assert body["created"] is False
    assert body["reason"] == "exact"
    assert body["duplicate_of"]["name"] == "Barbell Deadlift"


def test_create_novel_multiword_exercise_not_blocked(client):
    # A novel name with only loosely-similar catalog entries must save on the
    # spot (no false-positive "did you mean?" block). Regression for the
    # "lunge dumbbell overhead" case.
    r = client.post("/app/api/exercises", json={"name": "lunge dumbbell overhead"})
    assert r.status_code == 200
    body = r.json()
    assert body["created"] is True, body
    assert body["reason"] == "created"
    new_id = body["exercise"]["id"]

    # and it persists / is findable
    hits = client.get("/app/api/exercises/search", params={"q": "lunge dumbbell overhead"}).json()
    assert new_id in [h["exercise"]["id"] for h in hits]


def test_create_with_similar_hint_never_blocks(client):
    # A near-duplicate name must still create on the spot (never gated) and
    # surface the match as a non-blocking hint alongside the new exercise.
    from api.services.search import get_search_service

    svc = get_search_service()
    existing = client.get(
        "/app/api/exercises/search", params={"q": "Barbell Deadlift"}
    ).json()[0]["exercise"]

    # Force a deterministic hint: pin the existing exercise's name-only vector
    # to unit-x and the candidate embedding to the same direction, independent
    # of the real embedding model's behavior on this particular string pair.
    v = np.zeros(svc.settings.embed_dim, dtype=np.float32)
    v[0] = 1.0
    svc.name_vec.set(str(existing["id"]), v)
    try:
        with mock.patch("api.services.search.embed", return_value=v * 0.95):
            r = client.post("/app/api/exercises", json={"name": "Barbell Deadlift Variant XYZ"})
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
        "/app/api/exercises",
        json={"name": "Cossack Goblet Squat", "primary_muscles": ["quadriceps"], "force": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["created"] is True
    new_id = body["exercise"]["id"]
    assert body["exercise"]["provenance"] == "user"

    # Newly created exercise is immediately findable (FTS + vector indexed).
    r2 = client.get("/app/api/exercises/search", params={"q": "Cossack Goblet Squat"})
    ids = [h["exercise"]["id"] for h in r2.json()]
    assert new_id in ids


def test_alias_makes_exercise_findable(client):
    # Add a custom abbreviation to a canonical exercise, then find it by that alias.
    found = client.get("/app/api/exercises/search", params={"q": "Glute Ham Raise"}).json()
    ex_id = found[0]["exercise"]["id"]

    r = client.post(f"/app/api/exercises/{ex_id}/aliases", json={"alias_text": "GHR razor"})
    assert r.status_code == 200
    assert "GHR razor" in r.json()["aliases"]

    hit = client.get("/app/api/exercises/search", params={"q": "GHR razor"}).json()
    assert hit and hit[0]["exercise"]["id"] == ex_id


def test_get_exercise_404(client):
    assert client.get("/app/api/exercises/99999999").status_code == 404


def test_similar_exercises_ranks_substitutes_and_excludes_self(client):
    ex_id = _ex_id(client, "barbell bench press")
    r = client.get(f"/app/api/exercises/{ex_id}/similar", params={"limit": 8})
    assert r.status_code == 200
    suggestions = r.json()
    assert suggestions, "expected at least one substitute for a common press"
    # Never suggests the exercise being replaced.
    assert all(s["exercise"]["id"] != ex_id for s in suggestions)
    # Only usable substitutes — different-stimulus candidates are filtered out.
    assert all(s["verdict"] in {"equivalent", "comparable"} for s in suggestions)
    # A shared-pattern press (another chest push) should surface near the top.
    names = " ".join(s["exercise"]["name"].lower() for s in suggestions)
    assert "press" in names or "bench" in names
    # Equivalents rank ahead of comparables.
    ranks = [0 if s["verdict"] == "equivalent" else 1 for s in suggestions]
    assert ranks == sorted(ranks)


def test_similar_exercises_respects_limit(client):
    ex_id = _ex_id(client, "barbell bench press")
    r = client.get(f"/app/api/exercises/{ex_id}/similar", params={"limit": 3})
    assert r.status_code == 200
    assert len(r.json()) <= 3


def test_similar_exercises_404_for_unknown(client):
    assert client.get("/app/api/exercises/99999999/similar").status_code == 404


def _ex_id(client, q: str) -> int:
    return client.get("/app/api/exercises/search", params={"q": q}).json()[0]["exercise"]["id"]


def _log_finished_session(client, ex_id: int, name: str, sets: list[dict]) -> dict:
    ws = client.post("/app/api/workouts", json={"name": name}).json()
    se = client.post(f"/app/api/workouts/{ws['id']}/exercises", json={"exercise_id": ex_id}).json()
    for s in sets:
        client.post(f"/app/api/workouts/{ws['id']}/exercises/{se['id']}/sets", json=s)
    return client.post(f"/app/api/workouts/{ws['id']}/finish").json()


def test_history_returns_sessions_newest_first_with_full_set_detail(client):
    ex_id = _ex_id(client, "barbell deadlift")
    _log_finished_session(client, ex_id, "Day 1", [{"reps": 5, "weight": 225, "is_warmup": False}])
    _log_finished_session(client, ex_id, "Day 2", [{"reps": 5, "weight": 235, "is_warmup": False}])

    history = client.get(f"/app/api/exercises/{ex_id}/history").json()
    assert [s["session_name"] for s in history] == ["Day 2", "Day 1"]
    assert history[0]["sets"][0]["weight"] == 235
    assert history[0]["sets"][0]["is_warmup"] is False


def test_history_respects_limit(client):
    ex_id = _ex_id(client, "barbell deadlift")
    for i in range(3):
        _log_finished_session(client, ex_id, f"Day {i}", [{"reps": 5, "weight": 100 + i}])

    history = client.get(f"/app/api/exercises/{ex_id}/history", params={"limit": 2}).json()
    assert len(history) == 2


def test_history_surfaces_duration_seconds_for_a_timed_set(client):
    ex_id = _ex_id(client, "plank")
    _log_finished_session(
        client, ex_id, "Core", [{"duration_seconds": 45, "is_warmup": False}]
    )

    history = client.get(f"/app/api/exercises/{ex_id}/history").json()
    assert history[0]["sets"][0]["duration_seconds"] == 45
