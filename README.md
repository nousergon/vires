# Vires

> *vires acquirit eundo* — "it gathers strength as it goes."

[![CI](https://github.com/nousergon/vires/actions/workflows/ci.yml/badge.svg)](https://github.com/nousergon/vires/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/nousergon/vires/branch/main/graph/badge.svg)](https://codecov.io/gh/nousergon/vires)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-149ECA?logo=react&logoColor=white)](https://react.dev/)
[![PWA](https://img.shields.io/badge/PWA-installable-5A0FC8?logo=pwa&logoColor=white)](https://web.dev/progressive-web-apps/)

A strength-training tracker. Log workouts, build reusable routines, and find
exercises with **hybrid keyword + semantic search**. Mobile-first PWA — installable
to your phone's home screen, works like a native app.

This is the **tracking + exercise-library substrate** for a larger strength-coach
vision; the AI coach (multi-week program generation) is intentionally out of scope
for this MVP, but the data model is built to receive it.

## Features

- **Log workouts** — start empty or from a routine; sets × reps × weight, warm-up
  flags, per-set ✓ with an inline **rest countdown**, and a **hold timer** for
  isometric moves (planks, stretches).
- **Routines** — reusable templates with target sets/reps/weight/rest per exercise;
  starting a workout pre-fills the set rows (and "last time" carries forward).
- **Hybrid exercise search** — type `RDL` or describe a movement
  ("the hamstring curl where your feet are held down") and find it. The same
  embedding index detects near-duplicates when you add a custom exercise.
- **Offline-friendly PWA** with a chosen weight unit, configurable defaults, and
  full workout history.

## Stack

- **Backend:** FastAPI + SQLAlchemy (SQLite in dev → Postgres for multi-tenant).
- **Search:** local hybrid retrieval — SQLite FTS5 (BM25) ∥ FastEmbed
  (`bge-small-en-v1.5`, 384-d) cosine, fused with Reciprocal Rank Fusion. No API
  keys, no GPU. Same embedding index powers near-duplicate exercise detection.
- **Frontend:** React (Vite) + TypeScript + Tailwind, shipped as an installable PWA.

## Local development

Requires [uv](https://docs.astral.sh/uv/) and Node 20+.

```bash
# Backend (Python 3.13)
uv sync
uv run alembic upgrade head        # create the schema
uv run python -m api.db.seed       # seed the exercise catalog
uv run uvicorn api.main:app --reload   # http://127.0.0.1:8000

# Frontend
cd web && npm install && npm run dev    # http://127.0.0.1:5173
```

Run tests + lint:

```bash
uv run pytest
uv run ruff check .
```

## License

AGPL-3.0-only. See [LICENSE](LICENSE), [NOTICE](NOTICE), and
[CONTRIBUTING.md](CONTRIBUTING.md).
