"""Fetch + slim the free-exercise-db catalog into a vendored seed file.

Source: https://github.com/yuhonas/free-exercise-db  (The Unlicense / public
domain — verified AGPL-compatible). Run occasionally to refresh the catalog:

    uv run python scripts/fetch_exercise_seed.py

Writes ``api/db/seed_data/exercises.json`` (only the fields Vires uses; image
paths and per-exercise media are dropped to keep the repo lean).
"""

from __future__ import annotations

import json
import pathlib

import httpx

SOURCE_URL = (
    "https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/dist/exercises.json"
)
_ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT_PATH = _ROOT / "api" / "db" / "seed_data" / "exercises.json"

KEEP_FIELDS = (
    "name",
    "primaryMuscles",
    "secondaryMuscles",
    "equipment",
    "mechanic",
    "category",
    "force",
    "level",
    "instructions",
)


def main() -> None:
    resp = httpx.get(SOURCE_URL, timeout=60, follow_redirects=True)
    resp.raise_for_status()
    raw = resp.json()

    slim = [{k: ex.get(k) for k in KEEP_FIELDS} for ex in raw]
    slim.sort(key=lambda e: (e.get("name") or "").lower())

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(slim, indent=0, ensure_ascii=False))
    print(f"Wrote {len(slim)} exercises -> {OUT_PATH.relative_to(OUT_PATH.parent.parent.parent)}")


if __name__ == "__main__":
    main()
