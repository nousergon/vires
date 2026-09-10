# Security Policy

## Reporting a vulnerability

If you find a security vulnerability in Vires, please report it privately:

- **Preferred:** open a [GitHub Security Advisory](https://github.com/nousergon/vires/security/advisories/new). This keeps the discussion private until a fix ships.
- **Alternative:** email `security@nousergon.ai` with a description and reproduction steps.

Please **do not** open a public issue for security reports. I aim to acknowledge within 72 hours and ship a fix or mitigation within 14 days for high-severity issues.

## Scope

Vires is a strength-training tracker: FastAPI backend, React PWA frontend, SQLite via Alembic.
The sensitive surface is **account data and the auth boundary**. In scope:

- **Auth bypass / token forgery:** any path that forges or replays a `nousergon-auth`
  EdDSA/Ed25519 JWT, or that reaches a route without a valid JWKS-verified token
  (`api/services/auth_jwt.py`).
- **Cross-account data exposure:** any path that returns another user's workouts, routines,
  or objective/coach data.
- **Injection / traversal:** SQL injection against the SQLAlchemy layer, path traversal in
  GPX file handling (`api/services/geo/gpx.py`, guarded by `defusedxml` against
  entity-expansion/DTD attacks), or unsafe handling of push-notification payloads
  (`pywebpush`).
- **Supply-chain:** a dependency or install path that could execute untrusted code during
  `uv sync` or `npm ci`.

Out of scope:

- DoS via traffic volume.
- Vulnerabilities in upstream dependencies not yet publicly disclosed — report those
  upstream first.
- The proprietary programming/progression logic that lives in the private `vires-ops`
  companion repo — report those to the same channel above, but they are handled there.

## Threat model assumptions

- **Multi-tenant by design** (SQLite in dev, Postgres for production multi-tenant), so a
  cross-account data leak is treated as high severity even without further exploitation.
- **Auth is delegated to `nousergon-auth`** — this repo verifies JWTs against its JWKS, it
  does not issue or store credentials itself.
- **The coach/LLM path routes through the krepis router edge** — no direct provider API key
  lives in this repo's runtime config.
- **HTTPS** is assumed for all client/API and router-edge traffic.

## Hardening recommendations for self-hosters

- Keep any `.env` at `600` and never commit it; prefer SSM SecureStrings for any non-local
  deploy (see `infrastructure/`).
- Run Alembic migrations before serving traffic on a schema change — never hand-edit the
  SQLite file.
- Set provider-side spend limits on the coach path's router key.
