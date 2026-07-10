#!/bin/bash
# deploy-on-merge.sh — refresh deps, migrate + seed the DB, rebuild the PWA,
# sync nginx/systemd if changed, restart the service, health-check. Invoked via
# SSM from the deploy workflow AFTER the caller has pulled the repo to its ref.
#
# Runs as ec2-user (owns .venv + node_modules + build artifacts); sudo only for
# the nginx/systemd writes + restart (ec2-user has passwordless sudo). Output
# stays on stdout for the GHA deploy log. Exits non-zero on any failure (fail loud).
set -uo pipefail

REPO=/home/ec2-user/vires
PORT=8530
cd "$REPO"
echo "=== vires deploy $(date -u +%FT%TZ) — vires@$(git rev-parse --short HEAD) ==="

# --- Python deps (venv created at provision time; recreate if absent) -------- #
if [ ! -x .venv/bin/python ]; then
  echo "no venv — creating"; python3 -m venv .venv || { echo "venv FAILED"; exit 1; }
fi
.venv/bin/pip install -q --upgrade pip >/dev/null
.venv/bin/pip install -q . || { echo "pip install FAILED"; exit 1; }

# --- DB migrate + seed (idempotent) + build vector index if missing --------- #
.venv/bin/alembic upgrade head || { echo "alembic FAILED"; exit 1; }
.venv/bin/python -m api.db.seed || { echo "seed FAILED"; exit 1; }
if [ ! -f data/exercises.npz ]; then
  echo "building vector index (first run)"
  .venv/bin/python -m api.services.search || { echo "reindex FAILED"; exit 1; }
fi

# --- Web bundle: fetch the prebuilt artifact built in CI ---------------------- #
# The box does NOT build the frontend: it has Node 18 (Vite 8 needs 20+), the
# rolldown native binding is fragile to install cross-platform, and disk is tight.
# CI (deploy.yml) builds the bundle on a clean linux runner and uploads it here;
# the box just fetches + serves it. Keeps the box node-free and the deploy fast.
DIST_S3="${VIRES_DIST_S3:?VIRES_DIST_S3 not set (passed by the deploy workflow)}"
echo "fetching web bundle: ${DIST_S3}"
aws s3 cp "$DIST_S3" /tmp/vires-dist.tgz --quiet || { echo "web bundle fetch FAILED"; exit 1; }
rm -rf "$REPO/web/dist" && mkdir -p "$REPO/web/dist"
tar -xzf /tmp/vires-dist.tgz -C "$REPO/web/dist" || { echo "web bundle extract FAILED"; exit 1; }
rm -f /tmp/vires-dist.tgz

# --- nginx site: install/refresh our own conf file when it changed ----------- #
NGINX_SRC="$REPO/infrastructure/nginx.conf"
NGINX_LIVE="/etc/nginx/conf.d/vires.conf"
if ! sudo cmp -s "$NGINX_SRC" "$NGINX_LIVE" 2>/dev/null; then
  echo "nginx conf changed — installing"
  sudo cp "$NGINX_SRC" "$NGINX_LIVE"
  sudo nginx -t || { echo "nginx -t FAILED"; exit 1; }
  sudo systemctl reload nginx || { echo "nginx reload FAILED"; exit 1; }
fi

# --- systemd unit: install/refresh when it changed -------------------------- #
UNIT_SRC="$REPO/infrastructure/vires.service"
UNIT_LIVE="/etc/systemd/system/vires.service"
if ! sudo cmp -s "$UNIT_SRC" "$UNIT_LIVE" 2>/dev/null; then
  echo "systemd unit changed — installing"
  sudo cp "$UNIT_SRC" "$UNIT_LIVE"
  sudo systemctl daemon-reload
  sudo systemctl enable vires >/dev/null 2>&1 || true
fi

# --- AI coach secret: hydrate the Anthropic key from SSM into .env ---------- #
# Single source of truth is SSM Parameter Store; rotation = update the param +
# redeploy. The key value is NEVER echoed (CLI-output-safety rule). Missing key
# is NON-FATAL: the coach endpoints 503 and the rest of the app keeps working.
SSM_PARAM="${VIRES_ANTHROPIC_SSM_PARAM:-/vires/anthropic_api_key}"
ENV_FILE="$REPO/.env"
touch "$ENV_FILE"
if KEY=$(aws ssm get-parameter --name "$SSM_PARAM" --with-decryption \
           --query Parameter.Value --output text 2>/dev/null) \
   && [ -n "$KEY" ] && [ "$KEY" != "None" ]; then
  grep -v '^VIRES_ANTHROPIC_API_KEY=' "$ENV_FILE" > "$ENV_FILE.tmp" || true
  mv "$ENV_FILE.tmp" "$ENV_FILE"
  printf 'VIRES_ANTHROPIC_API_KEY=%s\n' "$KEY" >> "$ENV_FILE"   # value not traced (no set -x)
  chmod 600 "$ENV_FILE"
  unset KEY
  echo "coach: hydrated Anthropic key from ${SSM_PARAM}"
else
  echo "coach: no key at ${SSM_PARAM} — AI coach unavailable (non-fatal)"
fi

# --- Coaching edge: hydrate the tuned coach prompt from S3 (private) --------- #
# The tuned prompt is the Vires edge (Commercial-tier) — kept out of the public
# repo, stored in a private S3 bucket, written to the gitignored
# prompts/coach_system.txt. NOT SSM: parameter store caps out at 8192 chars
# even at Advanced tier, which the tuned prompt exceeded in practice
# (2026-07-08, see vires-ops/prompts/README.md) — S3 has no such ceiling.
# Missing is NON-FATAL: the committed coach_system.example.txt baseline is
# used instead.
PROMPT_S3="${VIRES_COACH_PROMPT_S3:-s3://vires-secrets/coach_system_prompt.txt}"
PROMPT_FILE="$REPO/api/services/coach/prompts/coach_system.txt"
if aws s3 cp "$PROMPT_S3" "$PROMPT_FILE" --only-show-errors 2>/dev/null \
   && [ -s "$PROMPT_FILE" ]; then
  chmod 600 "$PROMPT_FILE"
  echo "coach: hydrated tuned prompt from ${PROMPT_S3}"
else
  rm -f "$PROMPT_FILE"  # ensure we fall back to the committed baseline
  echo "coach: no tuned prompt at ${PROMPT_S3} — using public baseline (non-fatal)"
fi

# --- AI coach open-model provider: hydrate the OpenRouter key from SSM ------- #
# The coach's ACTIVE provider is the /vires/llm/coach SSM param (krepis adapter;
# flip live, no redeploy — e.g. "openrouter:moonshotai/kimi-k2.6"; rollback =
# put-parameter back to "anthropic:claude-haiku-4-5"). NON-FATAL: missing key
# => the coach 503s only while the active spec points at an OpenRouter provider.
OR_PARAM="${VIRES_OPENROUTER_SSM_PARAM:-/vires/openrouter_api_key}"
if ORKEY=$(aws ssm get-parameter --name "$OR_PARAM" --with-decryption \
             --query Parameter.Value --output text 2>/dev/null) \
   && [ -n "$ORKEY" ] && [ "$ORKEY" != "None" ]; then
  grep -v '^VIRES_OPENROUTER_API_KEY=' "$ENV_FILE" > "$ENV_FILE.tmp" || true
  mv "$ENV_FILE.tmp" "$ENV_FILE"
  printf 'VIRES_OPENROUTER_API_KEY=%s\n' "$ORKEY" >> "$ENV_FILE"   # value not traced (no set -x)
  chmod 600 "$ENV_FILE"
  unset ORKEY
  echo "coach: hydrated OpenRouter key from ${OR_PARAM}"
else
  echo "coach: no key at ${OR_PARAM} — open-model providers unavailable (non-fatal)"
fi

# --- Speech-to-text: hydrate the STT key from SSM into .env ------------------ #
# NON-FATAL: missing key => /coach/transcribe 503s and the mic is hidden client-side.
STT_PARAM="${VIRES_STT_SSM_PARAM:-/vires/stt_api_key}"
if STTKEY=$(aws ssm get-parameter --name "$STT_PARAM" --with-decryption \
              --query Parameter.Value --output text 2>/dev/null) \
   && [ -n "$STTKEY" ] && [ "$STTKEY" != "None" ]; then
  grep -v '^VIRES_STT_API_KEY=' "$ENV_FILE" > "$ENV_FILE.tmp" || true
  mv "$ENV_FILE.tmp" "$ENV_FILE"
  printf 'VIRES_STT_API_KEY=%s\n' "$STTKEY" >> "$ENV_FILE"   # value not traced (no set -x)
  chmod 600 "$ENV_FILE"
  unset STTKEY
  echo "stt: hydrated key from ${STT_PARAM}"
else
  echo "stt: no key at ${STT_PARAM} — voice input unavailable (non-fatal)"
fi

# --- Web Push: hydrate the VAPID keypair from SSM ---------------------------- #
# NON-FATAL: without both keys /push 503s and the client falls back to the
# foreground beep + wake-lock. Private key never echoed; public key is non-secret.
VAPID_PUB=$(aws ssm get-parameter --name "${VIRES_VAPID_PUBLIC_SSM_PARAM:-/vires/vapid_public_key}" \
              --query Parameter.Value --output text 2>/dev/null || true)
VAPID_PRIV=$(aws ssm get-parameter --name "${VIRES_VAPID_PRIVATE_SSM_PARAM:-/vires/vapid_private_key}" \
               --with-decryption --query Parameter.Value --output text 2>/dev/null || true)
if [ -n "$VAPID_PUB" ] && [ "$VAPID_PUB" != "None" ] \
   && [ -n "$VAPID_PRIV" ] && [ "$VAPID_PRIV" != "None" ]; then
  grep -vE '^VIRES_VAPID_(PUBLIC|PRIVATE)_KEY=' "$ENV_FILE" > "$ENV_FILE.tmp" || true
  mv "$ENV_FILE.tmp" "$ENV_FILE"
  printf 'VIRES_VAPID_PUBLIC_KEY=%s\n' "$VAPID_PUB" >> "$ENV_FILE"
  printf 'VIRES_VAPID_PRIVATE_KEY=%s\n' "$VAPID_PRIV" >> "$ENV_FILE"   # not traced (no set -x)
  chmod 600 "$ENV_FILE"
  unset VAPID_PRIV
  echo "push: hydrated VAPID keypair from SSM"
else
  echo "push: no VAPID keypair in SSM — locked-screen push unavailable (non-fatal)"
fi

# --- restart + health check ------------------------------------------------- #
sudo systemctl restart vires
sleep 4
curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null || { echo "vires health FAILED"; exit 1; }
echo "deploy OK — vires healthy on :${PORT}"
