## What & why

<!-- What does this change and why? Link any related issue. -->

## Checklist

- [ ] Tests added/updated for the behavior change (backend `tests/`, frontend `web/src/**/*.test.{ts,tsx}`)
- [ ] `uv run pytest --cov=api` passes locally — the backend coverage floor in `pyproject.toml` is a ratchet, raised as coverage improves and never lowered to make a change pass
- [ ] `npm run test -- --coverage` (in `web/`) passes locally — the frontend coverage floor in `vitest.config.ts` is the same kind of ratchet
- [ ] `uv run ruff check .` / `npm run lint` clean for files I touched
- [ ] Schema changes (if any) are an **Alembic migration**, never a hand-edit of `vires.db`
- [ ] Coverage badges are CI-generated onto the `badges` branch — no hand-edited badge URL or value

## Test plan

<!-- How you verified this works. -->

---

Prepared by: <model-name> via [Claude Code](https://claude.com/claude-code)
