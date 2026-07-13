"""Workout logging: start (empty/from-template), log sets, finish, history, prev-perf."""

from __future__ import annotations


def _ex_id(client, q: str) -> int:
    return client.get("/api/exercises/search", params={"q": q}).json()[0]["exercise"]["id"]


def _lower_body_template(client, name: str = "Legs") -> dict:
    e = _ex_id(client, "squat")
    return client.post(
        "/api/templates",
        json={
            "name": name,
            "exercises": [
                {"exercise_id": e, "target_sets": 3, "target_reps": 5, "target_weight": 100}
            ],
        },
    ).json()


def test_empty_workout_log_and_finish(client):
    ex = _ex_id(client, "barbell deadlift")
    ws = client.post("/api/workouts", json={"name": "Quick"}).json()
    assert ws["template_id"] is None and ws["exercises"] == []

    se = client.post(f"/api/workouts/{ws['id']}/exercises", json={"exercise_id": ex}).json()
    s1 = client.post(
        f"/api/workouts/{ws['id']}/exercises/{se['id']}/sets",
        json={"reps": 5, "weight": 225},
    ).json()
    assert s1["set_number"] == 1
    s2 = client.post(
        f"/api/workouts/{ws['id']}/exercises/{se['id']}/sets",
        json={"reps": 5, "weight": 235},
    ).json()
    assert s2["set_number"] == 2

    fin = client.post(f"/api/workouts/{ws['id']}/finish").json()
    assert fin["ended_at"] is not None
    assert len(fin["exercises"][0]["sets"]) == 2


def test_ad_hoc_exercise_with_target_sets_seeds_ready_to_fill_rows(client):
    # WorkoutPage's addExercise sends target_sets/target_reps from the user's
    # defaults — the server should pre-create matching set rows exactly like
    # a from-template exercise does, not leave the list empty.
    ex = _ex_id(client, "barbell deadlift")
    ws = client.post("/api/workouts", json={}).json()
    se = client.post(
        f"/api/workouts/{ws['id']}/exercises",
        json={"exercise_id": ex, "target_sets": 3, "target_reps": 8},
    ).json()
    assert len(se["sets"]) == 3
    assert all(s["reps"] == 8 for s in se["sets"])

    # Omitting target_sets stays a no-op (blank list, unchanged behavior).
    bare = client.post(
        f"/api/workouts/{ws['id']}/exercises", json={"exercise_id": ex}
    ).json()
    assert bare["sets"] == []


def test_start_from_template_clones_exercises(client):
    e1, e2 = _ex_id(client, "bench press"), _ex_id(client, "squat")
    tpl = client.post(
        "/api/templates",
        json={
            "name": "Full Body",
            "exercises": [
                {"exercise_id": e1, "target_sets": 3, "target_reps": 5, "rest_seconds": 120},
                {"exercise_id": e2, "target_sets": 3, "target_reps": 8},
            ],
        },
    ).json()
    ws = client.post("/api/workouts", json={"template_id": tpl["id"]}).json()
    assert ws["name"] == "Full Body"
    assert ws["template_id"] == tpl["id"]
    assert [se["exercise"]["id"] for se in ws["exercises"]] == [e1, e2]
    assert ws["exercises"][0]["target_sets"] == 3
    assert ws["exercises"][0]["rest_seconds"] == 120


# --------------------------------------------------------------------------- #
# Same-day ailment gate (vires-ops#58) — the Train tab's ad-hoc/template start
# used to skip this gate entirely (only /api/plan/planned/{id}/start had it,
# see test_plan.py). Mirrors those cases for POST /api/workouts.
# --------------------------------------------------------------------------- #
def test_starting_ad_hoc_workout_with_knee_severity_seven_surfaces_warning(client):
    tpl = _lower_body_template(client)
    client.post(
        "/api/ailments",
        json={"label": "Right knee", "onset_date": "2020-01-01", "initial_severity": 7},
    )

    r = client.post("/api/workouts", json={"template_id": tpl["id"]})
    assert r.status_code == 201, r.text
    se = r.json()["exercises"][0]
    assert se["notes"] is not None
    assert "knee" in se["notes"].lower()
    assert "7/10" in se["notes"]


def test_starting_ad_hoc_workout_with_knee_severity_eight_is_blocked(client):
    tpl = _lower_body_template(client)
    client.post(
        "/api/ailments",
        json={"label": "Right knee", "onset_date": "2020-01-01", "initial_severity": 8},
    )

    r = client.post("/api/workouts", json={"template_id": tpl["id"]})
    assert r.status_code == 409
    assert "knee" in r.json()["detail"].lower()


def test_starting_empty_workout_with_knee_severity_eight_is_blocked(client):
    # No template/exercises at all — the block is session-level, not tied to
    # any particular prescribed exercise.
    client.post(
        "/api/ailments",
        json={"label": "Right knee", "onset_date": "2020-01-01", "initial_severity": 8},
    )

    r = client.post("/api/workouts", json={})
    assert r.status_code == 409


def test_mild_knee_ailment_does_not_warn_or_block_ad_hoc_start(client):
    tpl = _lower_body_template(client)
    client.post(
        "/api/ailments",
        json={"label": "Right knee", "onset_date": "2020-01-01", "initial_severity": 3},
    )

    r = client.post("/api/workouts", json={"template_id": tpl["id"]})
    assert r.status_code == 201
    assert r.json()["exercises"][0]["notes"] is None


def test_start_from_template_seeds_planned_sets(client):
    e1 = _ex_id(client, "bench press")
    tpl = client.post(
        "/api/templates",
        json={
            "name": "Seeded",
            "exercises": [{"exercise_id": e1, "target_sets": 3, "target_reps": 8}],
        },
    ).json()
    ws = client.post("/api/workouts", json={"template_id": tpl["id"]}).json()
    se = ws["exercises"][0]
    assert len(se["sets"]) == 3  # planned rows pre-created
    assert se["sets"][0]["reps"] == 8  # prefilled from target reps
    assert se["sets"][0]["completed_at"] is None  # not done yet


def test_template_target_weight_seeds_set_weight(client):
    e1 = _ex_id(client, "bench press")
    tpl = client.post(
        "/api/templates",
        json={
            "name": "Weighted",
            "exercises": [
                {"exercise_id": e1, "target_sets": 2, "target_reps": 5, "target_weight": 135}
            ],
        },
    ).json()
    assert tpl["exercises"][0]["target_weight"] == 135
    ws = client.post("/api/workouts", json={"template_id": tpl["id"]}).json()
    se = ws["exercises"][0]
    assert se["target_weight"] == 135
    assert all(s["weight"] == 135 for s in se["sets"])  # planned sets seeded with it


def test_target_weight_used_despite_blank_prior_history(client):
    e1 = _ex_id(client, "bench press")
    # Prior session where the exercise was logged with NO weight (e.g. an
    # earlier planned set left blank) — must not suppress the routine's weight.
    w0 = client.post("/api/workouts", json={}).json()
    se0 = client.post(f"/api/workouts/{w0['id']}/exercises", json={"exercise_id": e1}).json()
    client.post(f"/api/workouts/{w0['id']}/exercises/{se0['id']}/sets", json={"reps": 5})
    client.post(f"/api/workouts/{w0['id']}/finish")

    tpl = client.post(
        "/api/templates",
        json={
            "name": "W",
            "exercises": [{"exercise_id": e1, "target_sets": 1, "target_weight": 135}],
        },
    ).json()
    ws = client.post("/api/workouts", json={"template_id": tpl["id"]}).json()
    assert ws["exercises"][0]["sets"][0]["weight"] == 135


def test_dumbbell_template_target_weight_seeds_per_hand(client):
    # "Dumbbell Bench Press" programmed at 90 (the bilateral total, e.g. a
    # pair of 45s) should seed the live session/set weight at 45 (per hand).
    ex = _ex_id(client, "dumbbell bench press")
    tpl = client.post(
        "/api/templates",
        json={
            "name": "Push",
            "exercises": [{"exercise_id": ex, "target_sets": 1, "target_weight": 90}],
        },
    ).json()
    assert tpl["exercises"][0]["target_weight"] == 90  # template stays total

    ws = client.post("/api/workouts", json={"template_id": tpl["id"]}).json()
    se = ws["exercises"][0]
    assert se["target_weight"] == 45
    assert se["sets"][0]["weight"] == 45

    # A non-dumbbell exercise is unaffected.
    barbell = _ex_id(client, "barbell bench press")
    tpl2 = client.post(
        "/api/templates",
        json={
            "name": "Push 2",
            "exercises": [{"exercise_id": barbell, "target_sets": 1, "target_weight": 90}],
        },
    ).json()
    ws2 = client.post("/api/workouts", json={"template_id": tpl2["id"]}).json()
    assert ws2["exercises"][0]["target_weight"] == 90


def test_timed_exercise_seeds_duration_and_flags(client):
    hits = client.get("/api/exercises/search", params={"q": "plank"}).json()
    plank = next(h["exercise"] for h in hits if h["exercise"]["name"].lower() == "plank")
    assert plank["is_timed"] is True
    tpl = client.post(
        "/api/templates",
        json={
            "name": "Core",
            "exercises": [
                {"exercise_id": plank["id"], "target_sets": 2, "target_duration_seconds": 60}
            ],
        },
    ).json()
    assert tpl["exercises"][0]["target_duration_seconds"] == 60
    ws = client.post("/api/workouts", json={"template_id": tpl["id"]}).json()
    se = ws["exercises"][0]
    assert se["exercise"]["is_timed"] is True
    assert se["target_duration_seconds"] == 60
    assert [s["duration_seconds"] for s in se["sets"]] == [60, 60]
    assert all(s["reps"] is None for s in se["sets"])  # timed: no reps


def test_mark_set_done_toggles_completed_at(client):
    ex = _ex_id(client, "barbell deadlift")
    ws = client.post("/api/workouts", json={}).json()
    se = client.post(f"/api/workouts/{ws['id']}/exercises", json={"exercise_id": ex}).json()
    s = client.post(
        f"/api/workouts/{ws['id']}/exercises/{se['id']}/sets", json={"reps": 5, "weight": 100}
    ).json()

    done = client.patch(
        f"/api/workouts/{ws['id']}/exercises/{se['id']}/sets/{s['id']}",
        json={"done": True, "weight": 105},
    ).json()
    assert done["completed_at"] is not None
    assert done["weight"] == 105

    undone = client.patch(
        f"/api/workouts/{ws['id']}/exercises/{se['id']}/sets/{s['id']}", json={"done": False}
    ).json()
    assert undone["completed_at"] is None


def test_started_at_is_timezone_aware(client):
    ws = client.post("/api/workouts", json={}).json()
    # tz-aware ISO so clients don't misread UTC as local (elapsed-timer fix)
    assert ws["started_at"].endswith("+00:00") or ws["started_at"].endswith("Z")


def test_previous_performance_hint(client):
    ex = _ex_id(client, "barbell curl")
    # First session: log 3x10@50, finish.
    w1 = client.post("/api/workouts", json={"name": "Day 1"}).json()
    se1 = client.post(f"/api/workouts/{w1['id']}/exercises", json={"exercise_id": ex}).json()
    for _ in range(3):
        client.post(
            f"/api/workouts/{w1['id']}/exercises/{se1['id']}/sets",
            json={"reps": 10, "weight": 50},
        )
    client.post(f"/api/workouts/{w1['id']}/finish")

    # Second session: adding the same exercise surfaces last time's sets.
    w2 = client.post("/api/workouts", json={"name": "Day 2"}).json()
    se2 = client.post(f"/api/workouts/{w2['id']}/exercises", json={"exercise_id": ex}).json()
    prev = se2["previous_performance"]
    assert prev is not None
    assert prev["session_id"] == w1["id"]
    assert len(prev["sets"]) == 3
    assert prev["sets"][0]["weight"] == 50


def test_previous_performance_hint_carries_duration_for_timed_exercise(client):
    hits = client.get("/api/exercises/search", params={"q": "plank"}).json()
    plank = next(h["exercise"] for h in hits if h["exercise"]["name"].lower() == "plank")

    w1 = client.post("/api/workouts", json={"name": "Day 1"}).json()
    se1 = client.post(
        f"/api/workouts/{w1['id']}/exercises", json={"exercise_id": plank["id"]}
    ).json()
    client.post(
        f"/api/workouts/{w1['id']}/exercises/{se1['id']}/sets",
        json={"duration_seconds": 45},
    )
    client.post(f"/api/workouts/{w1['id']}/finish")

    w2 = client.post("/api/workouts", json={"name": "Day 2"}).json()
    se2 = client.post(
        f"/api/workouts/{w2['id']}/exercises", json={"exercise_id": plank["id"]}
    ).json()
    prev = se2["previous_performance"]
    assert prev["sets"][0]["duration_seconds"] == 45


def test_history_list_and_volume(client):
    ex = _ex_id(client, "barbell deadlift")
    ws = client.post("/api/workouts", json={"name": "Vol"}).json()
    se = client.post(f"/api/workouts/{ws['id']}/exercises", json={"exercise_id": ex}).json()
    client.post(
        f"/api/workouts/{ws['id']}/exercises/{se['id']}/sets", json={"reps": 5, "weight": 100}
    )
    client.post(
        f"/api/workouts/{ws['id']}/exercises/{se['id']}/sets",
        json={"reps": 10, "weight": 0, "is_warmup": True},
    )
    rows = client.get("/api/workouts").json()
    row = next(r for r in rows if r["id"] == ws["id"])
    assert row["set_count"] == 2
    assert row["total_volume"] == 500.0  # warmup + zero-weight excluded


def test_update_and_delete_set(client):
    ex = _ex_id(client, "barbell deadlift")
    ws = client.post("/api/workouts", json={}).json()
    se = client.post(f"/api/workouts/{ws['id']}/exercises", json={"exercise_id": ex}).json()
    s = client.post(
        f"/api/workouts/{ws['id']}/exercises/{se['id']}/sets", json={"reps": 5, "weight": 100}
    ).json()

    upd = client.patch(
        f"/api/workouts/{ws['id']}/exercises/{se['id']}/sets/{s['id']}", json={"weight": 110}
    ).json()
    assert upd["weight"] == 110 and upd["reps"] == 5

    delr = client.delete(f"/api/workouts/{ws['id']}/exercises/{se['id']}/sets/{s['id']}")
    assert delr.status_code == 204
    got = client.get(f"/api/workouts/{ws['id']}").json()
    assert got["exercises"][0]["sets"] == []


def test_logged_set_completes_by_default_but_can_be_added_unchecked(client):
    ex = _ex_id(client, "barbell deadlift")
    ws = client.post("/api/workouts", json={}).json()
    se = client.post(f"/api/workouts/{ws['id']}/exercises", json={"exercise_id": ex}).json()
    sets_url = f"/api/workouts/{ws['id']}/exercises/{se['id']}/sets"
    # Direct log (no flag) => performed/completed, as records-from-history relies on.
    done = client.post(sets_url, json={"reps": 5, "weight": 100}).json()
    assert done["completed_at"] is not None
    # The app's "+ Add set" passes done=false => an empty row the user ticks off later.
    fresh = client.post(sets_url, json={"reps": 5, "weight": 100, "done": False}).json()
    assert fresh["completed_at"] is None


def test_update_session_exercise_rest_seconds(client):
    ex = _ex_id(client, "barbell deadlift")
    ws = client.post("/api/workouts", json={}).json()
    se = client.post(f"/api/workouts/{ws['id']}/exercises", json={"exercise_id": ex}).json()
    upd = client.patch(
        f"/api/workouts/{ws['id']}/exercises/{se['id']}", json={"rest_seconds": 120}
    ).json()
    assert upd["rest_seconds"] == 120


def test_reorder_session_exercises_by_swapping_order_index(client):
    e1, e2 = _ex_id(client, "bench press"), _ex_id(client, "squat")
    ws = client.post("/api/workouts", json={}).json()
    se1 = client.post(f"/api/workouts/{ws['id']}/exercises", json={"exercise_id": e1}).json()
    se2 = client.post(f"/api/workouts/{ws['id']}/exercises", json={"exercise_id": e2}).json()
    assert se1["order_index"] == 0 and se2["order_index"] == 1
    # Swap their order; the session should list them in the new order.
    client.patch(f"/api/workouts/{ws['id']}/exercises/{se1['id']}", json={"order_index": 1})
    client.patch(f"/api/workouts/{ws['id']}/exercises/{se2['id']}", json={"order_index": 0})
    got = client.get(f"/api/workouts/{ws['id']}").json()
    assert [se["exercise"]["id"] for se in got["exercises"]] == [e2, e1]


def test_reorder_session_exercises_batch(client):
    e1, e2, e3 = (
        _ex_id(client, "bench press"),
        _ex_id(client, "squat"),
        _ex_id(client, "deadlift"),
    )
    ws = client.post("/api/workouts", json={}).json()
    se1 = client.post(f"/api/workouts/{ws['id']}/exercises", json={"exercise_id": e1}).json()
    se2 = client.post(f"/api/workouts/{ws['id']}/exercises", json={"exercise_id": e2}).json()
    se3 = client.post(f"/api/workouts/{ws['id']}/exercises", json={"exercise_id": e3}).json()

    reordered = client.patch(
        f"/api/workouts/{ws['id']}/exercises/reorder",
        json={"exercise_ids": [se3["id"], se1["id"], se2["id"]]},
    ).json()
    assert [se["exercise"]["id"] for se in reordered] == [e3, e1, e2]
    assert [se["order_index"] for se in reordered] == [0, 1, 2]

    got = client.get(f"/api/workouts/{ws['id']}").json()
    assert [se["exercise"]["id"] for se in got["exercises"]] == [e3, e1, e2]


def test_reorder_session_exercises_rejects_mismatched_ids(client):
    e1 = _ex_id(client, "bench press")
    ws = client.post("/api/workouts", json={}).json()
    se1 = client.post(f"/api/workouts/{ws['id']}/exercises", json={"exercise_id": e1}).json()
    resp = client.patch(
        f"/api/workouts/{ws['id']}/exercises/reorder",
        json={"exercise_ids": [se1["id"], 999999]},
    )
    assert resp.status_code == 400


def test_workout_404(client):
    assert client.get("/api/workouts/99999999").status_code == 404


# --------------------------------------------------------------------------- #
# Per-workout tracking: tags (+ custom inputs, including what was eaten/drunk/
# supplemented pre-workout), and the end-of-session 1–10 energy/intensity
# self-report.
# --------------------------------------------------------------------------- #
def test_start_workout_with_tags(client):
    ws = client.post(
        "/api/workouts",
        json={
            "name": "Push day",
            "tags": ["push", "fasted", "6am garage", "black coffee", "creatine"],
        },
    ).json()
    assert ws["tags"] == ["push", "fasted", "6am garage", "black coffee", "creatine"]
    assert ws["energy_level"] is None and ws["workout_intensity"] is None
    # Defaults when omitted.
    bare = client.post("/api/workouts", json={"name": "Bare"}).json()
    assert bare["tags"] == []


def test_workout_tags_endpoint_ranks_by_frequency_then_alpha(client):
    client.post("/api/workouts", json={"name": "A", "tags": ["push", "coffee"]})
    client.post("/api/workouts", json={"name": "B", "tags": ["push", "banana"]})
    client.post("/api/workouts", json={"name": "C", "tags": ["push"]})
    tags = client.get("/api/workouts/tags").json()
    # "push" used 3x outranks "banana"/"coffee" (1x each, alpha tiebreak).
    assert tags == ["push", "banana", "coffee"]


def test_finish_records_energy_intensity_and_challenge(client):
    ws = client.post("/api/workouts", json={"name": "Legs"}).json()
    fin = client.post(
        f"/api/workouts/{ws['id']}/finish",
        json={"energy_level": 7, "workout_intensity": 9, "challenge_level": 3},
    ).json()
    assert fin["ended_at"] is not None
    assert fin["energy_level"] == 7
    assert fin["workout_intensity"] == 9
    assert fin["challenge_level"] == 3


def test_finish_ratings_out_of_range_rejected(client):
    ws = client.post("/api/workouts", json={"name": "X"}).json()
    assert (
        client.post(
            f"/api/workouts/{ws['id']}/finish", json={"energy_level": 11}
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/workouts/{ws['id']}/finish", json={"workout_intensity": 0}
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/workouts/{ws['id']}/finish", json={"challenge_level": 0}
        ).status_code
        == 422
    )


def test_finish_without_body_still_closes_session(client):
    ws = client.post("/api/workouts", json={"name": "NoRating"}).json()
    fin = client.post(f"/api/workouts/{ws['id']}/finish").json()
    assert fin["ended_at"] is not None
    assert fin["energy_level"] is None
    assert fin["workout_intensity"] is None
    assert fin["challenge_level"] is None


def test_ratings_can_be_filled_in_after_finishing(client):
    ws = client.post("/api/workouts", json={"name": "Later"}).json()
    client.post(f"/api/workouts/{ws['id']}/finish")  # closed, no ratings
    fin = client.post(
        f"/api/workouts/{ws['id']}/finish",
        json={"energy_level": 5, "workout_intensity": 6, "challenge_level": 8},
    ).json()
    assert fin["energy_level"] == 5
    assert fin["workout_intensity"] == 6
    assert fin["challenge_level"] == 8


def test_patch_session_tracking_fields(client):
    ws = client.post("/api/workouts", json={"name": "Edit me"}).json()
    patched = client.patch(
        f"/api/workouts/{ws['id']}",
        json={
            "tags": ["deload", "banana"],
            "energy_level": 8,
            "workout_intensity": 4,
            "challenge_level": 2,
        },
    ).json()
    assert patched["tags"] == ["deload", "banana"]
    assert patched["energy_level"] == 8
    assert patched["workout_intensity"] == 4
    assert patched["challenge_level"] == 2


def test_tracking_fields_surface_in_history_list(client):
    ws = client.post(
        "/api/workouts", json={"name": "Traced", "tags": ["morning"]}
    ).json()
    client.post(
        f"/api/workouts/{ws['id']}/finish",
        json={"energy_level": 6, "workout_intensity": 7, "challenge_level": 9},
    )
    row = next(w for w in client.get("/api/workouts").json() if w["id"] == ws["id"])
    assert row["tags"] == ["morning"]
    assert row["energy_level"] == 6
    assert row["workout_intensity"] == 7
    assert row["challenge_level"] == 9


# --- offline-first set logging: client_uuid idempotency (vires-ops#48) -------- #
def _session_with_exercise(client):
    ex = _ex_id(client, "barbell deadlift")
    ws = client.post("/api/workouts", json={"name": "Offline"}).json()
    se = client.post(
        f"/api/workouts/{ws['id']}/exercises", json={"exercise_id": ex}
    ).json()
    return ws, se


def test_log_set_echoes_client_uuid(client):
    ws, se = _session_with_exercise(client)
    uuid = "11111111-1111-4111-8111-111111111111"
    s = client.post(
        f"/api/workouts/{ws['id']}/exercises/{se['id']}/sets",
        json={"reps": 5, "weight": 225, "client_uuid": uuid},
    ).json()
    assert s["client_uuid"] == uuid


def test_replayed_set_is_deduped_on_client_uuid(client):
    """A queued offline write replayed twice must create exactly one row and
    return the same set both times (append-wins on client UUID)."""
    ws, se = _session_with_exercise(client)
    uuid = "22222222-2222-4222-8222-222222222222"
    body = {"reps": 5, "weight": 225, "client_uuid": uuid}
    r1 = client.post(
        f"/api/workouts/{ws['id']}/exercises/{se['id']}/sets", json=body
    )
    r2 = client.post(
        f"/api/workouts/{ws['id']}/exercises/{se['id']}/sets", json=body
    )
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]  # same row, not a duplicate
    fin = client.get(f"/api/workouts/{ws['id']}").json()
    assert len(fin["exercises"][0]["sets"]) == 1


def test_distinct_client_uuids_create_distinct_sets(client):
    ws, se = _session_with_exercise(client)
    a = client.post(
        f"/api/workouts/{ws['id']}/exercises/{se['id']}/sets",
        json={"reps": 5, "client_uuid": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"},
    ).json()
    b = client.post(
        f"/api/workouts/{ws['id']}/exercises/{se['id']}/sets",
        json={"reps": 5, "client_uuid": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"},
    ).json()
    assert a["id"] != b["id"]
    assert a["set_number"] == 1 and b["set_number"] == 2


def test_log_set_without_client_uuid_still_works(client):
    """Online writes send no UUID; behavior (and null echo) unchanged."""
    ws, se = _session_with_exercise(client)
    s = client.post(
        f"/api/workouts/{ws['id']}/exercises/{se['id']}/sets",
        json={"reps": 8, "weight": 100},
    ).json()
    assert s["client_uuid"] is None
    assert s["set_number"] == 1


def test_same_uuid_under_different_exercises_is_not_deduped(client):
    """The dedup is scoped per session_exercise — the same UUID under a
    different exercise is a distinct set (NULLs/collisions can't cross rows)."""
    ex2 = _ex_id(client, "bench press")
    ws, se1 = _session_with_exercise(client)
    se2 = client.post(
        f"/api/workouts/{ws['id']}/exercises", json={"exercise_id": ex2}
    ).json()
    uuid = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
    r1 = client.post(
        f"/api/workouts/{ws['id']}/exercises/{se1['id']}/sets",
        json={"reps": 5, "client_uuid": uuid},
    )
    r2 = client.post(
        f"/api/workouts/{ws['id']}/exercises/{se2['id']}/sets",
        json={"reps": 5, "client_uuid": uuid},
    )
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.json()["id"] != r2.json()["id"]
