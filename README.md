# Vires

> *vires acquirit eundo* — "it gathers strength as it goes."

A strength-training tracker. Log workouts, build reusable routines, and find
exercises with hybrid keyword + semantic search. Web-based, mobile-first PWA
(installable to your phone's home screen).

This is the **tracking + exercise-library substrate** for a larger strength-coach
vision; the AI coach (multi-week program generation) is intentionally out of scope
for this MVP, but the data model is built to receive it.

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
