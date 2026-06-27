# Vires — one-time go-live runbook

After this runbook, every push to `main` auto-deploys via `.github/workflows/deploy.yml`
(OIDC → SSM → `deploy-on-merge.sh`). The host runs FastAPI behind nginx; CI builds the
PWA and ships it to S3, and the host fetches + serves it.

**App:** `https://<your-domain>` · **local port:** `8530`.

Host requirements: a Linux box with nginx + an SSM agent, **Python 3.11+** and a TLS
origin cert for your domain. Vires vendors its own Python venv and a pinned Node 20
(`.node/`, used only to *not* be needed at runtime — the frontend is built in CI), so it
doesn't depend on the host's system Node/Python versions.

Configure these GitHub Actions **Variables** (repo Settings → Secrets and variables →
Actions): `AWS_DEPLOY_ROLE_ARN`, `VIRES_INSTANCE_ID`, `VIRES_DIST_S3`.

## 1. DNS
Point your domain (or subdomain) at the host. If fronting with Cloudflare, use an
origin cert that the nginx site (`infrastructure/nginx.conf`) references.

## 2. Clone the repo onto the host
```
sudo -u ec2-user git clone https://github.com/nousergon/vires.git /home/ec2-user/vires
```

## 3. Create the venv (Python 3.11+)
```
cd /home/ec2-user/vires && sudo -u ec2-user python3.11 -m venv .venv
```

## 4. First deploy (installs deps, migrates, seeds, fetches web bundle, nginx + systemd, starts)
The host does NOT build the frontend — CI builds the PWA and uploads it to
`$VIRES_DIST_S3`; the host fetches it. So either run the deploy workflow once first (it
builds + uploads the bundle), or seed the bundle manually:
`tar -czf - -C web/dist . | aws s3 cp - "$VIRES_DIST_S3"`. Then on the host:
```
sudo -u ec2-user VIRES_DIST_S3="$VIRES_DIST_S3" bash /home/ec2-user/vires/infrastructure/deploy-on-merge.sh
```
Idempotent; exactly what CI runs each merge. First run downloads the embedding model
(~13 MB) + builds the vector index. Health check hits `http://127.0.0.1:8530/health`.

## 5. Wire CI auto-deploy
Set the Actions Variables above (`AWS_DEPLOY_ROLE_ARN`, `VIRES_INSTANCE_ID`,
`VIRES_DIST_S3`). The IAM role must be allowed `ssm:SendCommand` to the instance and
`s3:GetObject`/`PutObject` on the bundle path. Confirm with a `workflow_dispatch` run of
"Deploy Vires via SSM".

## 6. Verify
`curl https://<your-domain>/health` → 200, then open on your phone and
**Add to Home Screen**.

## Notes
- No app secrets in the MVP (single hardcoded dev user). When auth lands, hydrate
  secrets from SSM Parameter Store into `.env` in `deploy-on-merge.sh`.
- The SQLite DB lives at `/home/ec2-user/vires/vires.db` (not in git) — back it up.
