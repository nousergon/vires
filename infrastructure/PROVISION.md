# Vires — one-time go-live on the shared `*.nousergon.ai` box

After this runbook, every push to `main` auto-deploys via `.github/workflows/deploy.yml`
(OIDC → SSM → `deploy-on-merge.sh`), exactly like Metron / the dashboard.

**Target box:** `i-09b539c844515d549` (shared — also runs Metron + the dashboard).
**App URL:** `https://vires.nousergon.ai` · **local port:** `8530`.

Box facts (probed 2026-06-27): Amazon Linux, x86_64, system Node 18 + Python 3.9
(with `python3.11` available), nginx with `*.nousergon.ai` Cloudflare origin cert at
`/etc/ssl/certs/cloudflare-origin.pem`. Vires vendors its own Python 3.11 venv and a
pinned Node 20 (`.node/`) so it touches neither the system Node 18 (Metron's Next.js
build) nor system Python. ⚠️ Disk was 85% full (~2.5 G free) — watch it.

## 1. Cloudflare DNS
Add a proxied A record `vires.nousergon.ai` → the box's public/Elastic IP (same target
as `console`/`metron`). Orange-cloud on; the origin cert already covers `*.nousergon.ai`.

## 2. Clone the repo onto the box (private repo → needs box git auth)
Use the same credential mechanism the box already uses for the private `metron` repo
(deploy key / token). Via SSM as `ec2-user`:
```
sudo -u ec2-user git clone https://github.com/nousergon/vires.git /home/ec2-user/vires
```

## 3. Create the venv with Python 3.11 (system python3 is 3.9, too old)
```
cd /home/ec2-user/vires && sudo -u ec2-user python3.11 -m venv .venv
```

## 4. First deploy (installs deps, migrates, seeds, builds web, nginx + systemd, starts)
```
sudo -u ec2-user bash /home/ec2-user/vires/infrastructure/deploy-on-merge.sh
```
This is idempotent and is exactly what CI runs on every merge. First run downloads the
embedding model (~13 MB) + Node 20 (~30 MB) + builds the vector index. Health check hits
`http://127.0.0.1:8530/health`.

## 5. Wire CI auto-deploy
```
gh variable set VIRES_INSTANCE_ID --repo nousergon/vires --body i-09b539c844515d549
```
The OIDC role `github-actions-lambda-deploy` must be allowed `ssm:SendCommand` to this
instance (already granted for Metron/dashboard, same box). Confirm with a
`workflow_dispatch` run of "Deploy Vires via SSM".

## 6. Verify
`curl https://vires.nousergon.ai/health` → 200, then open on your phone and
**Add to Home Screen**.

## Notes / future
- No app secrets in the MVP (single hardcoded dev user). When auth lands, hydrate
  `/vires/*` SSM params into `.env` in `deploy-on-merge.sh` (mirror Metron's block).
- SQLite DB lives at `/home/ec2-user/vires/vires.db` (not in git). Back up alongside
  the other box SQLite DBs.
