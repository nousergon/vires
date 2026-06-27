"""Exercise search, dedup, alias, and history endpoint tests."""

from __future__ import annotations


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
