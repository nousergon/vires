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
Actions): `VIRES_INSTANCE_ID`, `VIRES_DIST_S3`. The deploy role is not a variable: its ARN
is written into `.github/workflows/deploy.yml` (`role-to-assume`), so a self-hosted fork
edits it there.

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
Set the Actions Variables above (`VIRES_INSTANCE_ID`, `VIRES_DIST_S3`) and point
`role-to-assume` in `deploy.yml` at your role. The IAM role must be allowed
`ssm:SendCommand` to the instance and `s3:GetObject`/`PutObject` on the bundle path, and
its trust policy must accept this workflow on `main`. Confirm with a `workflow_dispatch` run of
"Deploy Vires via SSM".

## 6. Verify
`curl https://<your-domain>/health` → 200, then open on your phone and
**Add to Home Screen**.

## 7. AI coach model route (optional — enables the ✨ Coach)
The coach calls no provider directly and needs no provider key on this host. It resolves
the `low` model group through the krepis router (`api/services/coach/agent.py`,
`_default_spec`) and only accepts a compelled route (`litellm_proxy`, or the DLP-scanned
`egress_proxy` fallback). The router edge resolves its own credentials. Do **not**
create a provider key parameter for vires: `deploy-on-merge.sh` hydrates none, and it scrubs
any `VIRES_ANTHROPIC_API_KEY` / `VIRES_OPENROUTER_API_KEY` line a prior deploy left in `.env`.
**It's non-fatal:** if the router group does not resolve, the deploy still succeeds and the
coach endpoints return 503 (the calendar/view/start/manual-schedule features keep working).
To pin which model the router edge serves, set `VIRES_COACH_LLM` or the `/vires/llm/coach`
SSM parameter (60s TTL, no redeploy) to `litellm_proxy:<model>`. A value that names any
other provider is refused with a 503 (`_reject_non_router_override`), so leave both unset
to use the router default.

### 7a. Tuned coach prompt (optional — the private edge)
The coach's system prompt is the Vires *edge* (Commercial-tier), so the public repo
ships only a competent, deliberately generic **baseline**
(`api/services/coach/prompts/coach_system.example.txt`) — no coaching methodology, just
the schema mechanism needed to work out of the box.
To run a tuned/private prompt in prod, store it in a private S3 bucket — NOT SSM (Parameter
Store caps out at 8192 chars even at Advanced tier, too small once the tuned prompt has real
depth). `deploy-on-merge.sh` fetches it to the gitignored `coach_system.txt` on each deploy
(content never logged):
```
aws s3 cp <prompt-file> s3://vires-secrets/coach_system_prompt.txt --sse AES256
```
Grant the instance role `s3:GetObject` on that bucket/key; override the path with
`VIRES_COACH_PROMPT_S3`. **Non-fatal:** with no prompt object the deploy succeeds and the
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

### 7d. Magic-link email (RETIRED)
Sign-in moved to the shared nousergon-auth service (vires-ops#60), and nothing in `api/`
reads a Resend key any more. `deploy-on-merge.sh` no longer hydrates one; it scrubs any
`VIRES_RESEND_API_KEY` a prior deploy left in `.env`.

### Revoking an optional key (§7b, §7c)
`deploy-on-merge.sh` converges each optional key three ways
(`infrastructure/lib/optional_ssm_env.sh`): a present parameter is written to `.env`; a
**confirmed `ParameterNotFound`** removes the key from `.env`; any other failure
(AccessDenied, throttling, network) is treated as unknown and leaves `.env` untouched, so a
transient AWS error never switches a feature off. Settings are cached for the life of the
process, so revocation takes effect when the deploy restarts the service; the feature's
endpoint then returns 503 before any outbound call.

## Notes
- App secrets (all optional, SSM- or S3-hydrated into the box, never committed): the tuned
  coach prompt (§7a), the speech-to-text key (§7b) and the VAPID keypair (§7c).
- The SQLite DB lives at `/home/ec2-user/vires/vires.db` (not in git) — back it up.
