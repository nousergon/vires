"""Pure-unit tests for the core logic (no DB / no HTTP)."""

from __future__ import annotations

from datetime import UTC, datetime

from api.db.fts import build_keywords
from api.db.seed import normalize_name
from api.db.types import UTCDateTime
from api.services.search import _fts_match_query, get_search_service


def test_normalize_name():
    assert normalize_name("  Barbell   Deadlift ") == "barbell deadlift"
    assert normalize_name("RDL") == "rdl"


def test_build_keywords_flattens_metadata():
    kw = build_keywords(
        aliases=["RDL"],
        primary_muscles=["hamstrings"],
        equipment="barbell",
        category="strength",
    )
    assert "RDL" in kw and "hamstrings" in kw and "barbell" in kw and "strength" in kw


def test_fts_match_query_tokenizes_and_prefixes():
    assert _fts_match_query("RDL") == '"rdl"*'
    assert _fts_match_query("pull-up bar") == '"pull"* OR "up"* OR "bar"*'
    assert _fts_match_query("   ") is None  # no tokens


def test_rrf_rewards_agreement_across_retrievers():
    svc = get_search_service()
    # id 2 appears in both ranked lists; should outrank ids in only one.
    scores = svc._rrf([[1, 2, 3], [2, 4, 5]])
    assert max(scores, key=scores.get) == 2
    assert scores[2] > scores[1]


def test_utcdatetime_roundtrip():
    t = UTCDateTime()
    naive = t.process_bind_param(datetime(2026, 1, 1, 12, 0, tzinfo=UTC), None)
    assert naive is not None and naive.tzinfo is None  # stored naive (SQLite)
    aware = t.process_result_value(naive, None)
    assert aware is not None and aware.tzinfo is UTC and aware.hour == 12
