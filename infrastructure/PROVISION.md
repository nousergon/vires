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

## 7. AI coach key (optional — enables the ✨ Coach)
The AI coach calls Anthropic. `deploy-on-merge.sh` hydrates the key from SSM into
`.env` on every deploy (quietly; the value is never logged). To enable it:
```
aws ssm put-parameter --name /vires/anthropic_api_key --type SecureString --value sk-ant-... 
```
and grant the instance role `ssm:GetParameter` on `arn:aws:ssm:<region>:<acct>:parameter/vires/anthropic_api_key`.
Override the path with the `VIRES_ANTHROPIC_SSM_PARAM` env var if you reuse an existing
parameter. **It's non-fatal:** with no key the deploy still succeeds and the coach
endpoints return 503 (the calendar/view/start/manual-schedule features keep working).
The model is set by `VIRES_COACH_MODEL` (default `claude-haiku-4-5`; bump to
`claude-sonnet-4-6` for stronger plans).

### 7a. Tuned coach prompt (optional — the private edge)
The coach's system prompt is the Vires *edge* (Commercial-tier), so the public repo
ships only a competent **baseline** (`api/services/coach/prompts/coach_system.example.txt`).
To run a tuned/private prompt in prod, store it in SSM — `deploy-on-merge.sh` writes it to
the gitignored `coach_system.txt` on each deploy (content never logged):
```
aws ssm put-parameter --name /vires/coach_system_prompt --type SecureString --value "<prompt>"
```
Grant the instance role `ssm:GetParameter` on that parameter; override the path with
`VIRES_COACH_PROMPT_SSM_PARAM`. **Non-fatal:** with no SSM prompt the deploy succeeds and the
baseline is used. The canonical tuned prompt lives in the private `nousergon/vires-ops` repo.

### 7b. Speech-to-text (optional — enables the coach mic)
The coach can take voice input via an OpenAI-compatible Whisper endpoint. `deploy-on-merge.sh`
hydrates the key from SSM (quietly):
```
aws ssm put-parameter --name /vires/stt_api_key --type SecureString --value sk-...
```
Grant the instance role `ssm:GetParameter` on it; override the path with `VIRES_STT_SSM_PARAM`.
Set `VIRES_STT_MODEL` (default `whisper-1`) and `VIRES_STT_BASE_URL` (default OpenAI; point at
Groq for cheaper/faster). **Non-fatal:** with no key the deploy succeeds, `/coach/transcribe`
returns 503, and the mic button is hidden client-side.

### 7c. Web Push (optional — locked-screen timer alerts)
Generate a VAPID keypair and store it in SSM; `deploy-on-merge.sh` hydrates both on each deploy:
```
python scripts/gen_vapid.py
aws ssm put-parameter --name /vires/vapid_public_key  --type String      --value "<public>"
aws ssm put-parameter --name /vires/vapid_private_key --type SecureString --value "<private>"
```
Grant the instance role `ssm:GetParameter` on both (override paths with
`VIRES_VAPID_PUBLIC_SSM_PARAM` / `VIRES_VAPID_PRIVATE_SSM_PARAM`). **Non-fatal:** without the
keypair `/push/*` returns 503 and the app falls back to the foreground beep + wake-lock.
**iOS:** Web Push only works for an **installed** PWA (Add to Home Screen) on iOS 16.4+, with
notification permission granted. The scheduler is in-process (single uvicorn proc) — a pending
alert is lost if the box restarts mid-rest; rare and short-lived.

## Notes
- App secrets (all optional, SSM-hydrated into the box, never committed): the AI-coach
  Anthropic key (§7) and the tuned coach prompt (§7a). The MVP otherwise runs as one
  hardcoded dev user with no secrets.
- The SQLite DB lives at `/home/ec2-user/vires/vires.db` (not in git) — back it up.
