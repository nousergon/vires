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

# --- AI coach: direct-Anthropic key hydration RETIRED (2026-08-29 ruling) --- #
# The coach funnels through the krepis router edge (api/services/coach/agent.py
# _default_spec / _reject_non_router_override) — it never constructs a direct
# Anthropic client any more, so there is no VIRES_ANTHROPIC_API_KEY consumer
# left to hydrate. Scrub any key a prior deploy left in .env rather than leave
# a live, unused credential on the box (vires-ops-I80 tracks deleting the now-
# orphaned /vires/anthropic_api_key SSM parameter).
ENV_FILE="$REPO/.env"
touch "$ENV_FILE"
grep -v '^VIRES_ANTHROPIC_API_KEY=' "$ENV_FILE" > "$ENV_FILE.tmp" || true
mv "$ENV_FILE.tmp" "$ENV_FILE"
chmod 600 "$ENV_FILE"

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

# --- AI coach open-model provider -------------------------------------------- #
# No direct-provider key (OpenRouter, Anthropic, or otherwise) is hydrated
# here. Removed alpha-engine-config-I9092 (2026-08-28) for OpenRouter, then
# generalized 2026-08-29 (Brian ruling: every LLM call funnels through the
# krepis router, no other parallel setups) — the coach's /vires/llm/coach SSM
# flip param can no longer resolve to ANY direct-provider linkage;
# api.services.coach.agent._reject_non_router_override refuses any spec whose
# provider isn't the router edge itself before a key is ever looked up, and
# no settings field holds a credential for a linkage that can never legally
# be used. Hydrating a key here would only stand up a credential nothing in
# the coach can legally use.
grep -v '^VIRES_OPENROUTER_API_KEY=' "$ENV_FILE" > "$ENV_FILE.tmp" 2>/dev/null || true
[ -f "$ENV_FILE.tmp" ] && mv "$ENV_FILE.tmp" "$ENV_FILE"  # scrub any key from a prior deploy

# --- LLM SFT capture: hydrate the capture flag from SSM into .env ------------- #
# Coach invocations gate SFT distillation rows on LLM_SFT_CAPTURE_ENABLED
# (krepis.llm_capture). Defaults to "true" per EPIC I1658 intent: distillation
# rows should accrue from day one for single-tenant owner deployments. Flip to
# "false" via the SSM param to disable capture without redeploying.
# NON-FATAL: missing param => default-on; capture accrues automatically.
SFT_PARAM="${VIRES_SFT_CAPTURE_SSM_PARAM:-/vires/llm_sft_capture_enabled}"
SFT_VALUE=$(aws ssm get-parameter --name "$SFT_PARAM" --query Parameter.Value --output text 2>/dev/null || true)
if [ -n "$SFT_VALUE" ] && [ "$SFT_VALUE" != "None" ]; then
  echo "coach: SFT capture flag from SSM: ${SFT_VALUE}"
else
  echo "coach: no SFT capture flag at ${SFT_PARAM} — defaulting to true"
  SFT_VALUE="true"
fi
grep -v '^LLM_SFT_CAPTURE_ENABLED=' "$ENV_FILE" > "$ENV_FILE.tmp" || true
mv "$ENV_FILE.tmp" "$ENV_FILE"
printf 'LLM_SFT_CAPTURE_ENABLED=%s\n' "$SFT_VALUE" >> "$ENV_FILE"
chmod 600 "$ENV_FILE"
unset SFT_VALUE

# --- Optional secrets: converge SSM -> .env (vires-ops#82, PROD-06) --------- #
# Each optional key is three-state (infrastructure/lib/optional_ssm_env.sh):
# present -> written; CONFIRMED ParameterNotFound -> REMOVED from .env, so
# deleting the parameter and redeploying actually revokes it; anything else
# (AccessDenied, network, throttling) is unknown and leaves .env untouched, so a
# transient AWS failure never switches a working feature off. All NON-FATAL.
# shellcheck source=lib/optional_ssm_env.sh
. "$REPO/infrastructure/lib/optional_ssm_env.sh"

# Speech-to-text: without the key /coach/transcribe 503s before any outbound call.
hydrate_optional_key "${VIRES_STT_SSM_PARAM:-/vires/stt_api_key}" VIRES_STT_API_KEY stt

# Web Push VAPID keypair: without both keys /push 503s and the client falls back
# to the foreground beep + wake-lock. The public key is non-secret.
hydrate_optional_pair \
  "${VIRES_VAPID_PUBLIC_SSM_PARAM:-/vires/vapid_public_key}" VIRES_VAPID_PUBLIC_KEY "" \
  "${VIRES_VAPID_PRIVATE_SSM_PARAM:-/vires/vapid_private_key}" VIRES_VAPID_PRIVATE_KEY --with-decryption \
  push

# --- Magic-link email: Resend key hydration RETIRED --------------------------- #
# vires-ops#60 moved sign-in to the shared nousergon-auth service and retired the
# magic-link endpoints; nothing in api/ reads VIRES_RESEND_API_KEY any more.
# Scrub any key a prior deploy left in .env rather than keep a live, unused
# credential on the box (same treatment as the retired Anthropic key above).
env_clear VIRES_RESEND_API_KEY

# --- restart + health check ------------------------------------------------- #
# Poll /health until uvicorn has bound the port, up to a deadline, instead of a
# fixed sleep. A single probe 4s after restart raced uvicorn's import time:
# deploys 2026-10-06, 10-12, 10-14 and 10-15 failed with `curl: (7) Failed to
# connect to 127.0.0.1 port 8530 after 0 ms` (nothing listening yet) while the
# next deploy of the same box passed — startup time varies with a fresh
# `pip install` (cold .pyc) and box load, so 4s was sometimes too short.
# On timeout the unit status + journal tail go to stdout, so the GHA log shows
# WHY the service did not come up rather than only that it did not.
sudo systemctl restart vires
HEALTH_DEADLINE_S="${VIRES_HEALTH_DEADLINE_S:-90}"
waited=0
until curl -fsS -m 5 "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; do
  if [ "$waited" -ge "$HEALTH_DEADLINE_S" ]; then
    echo "vires health FAILED — no healthy response on :${PORT} within ${HEALTH_DEADLINE_S}s"
    sudo systemctl status vires --no-pager -l 2>&1 | tail -n 20 || true
    sudo journalctl -u vires --no-pager -n 60 --since "-$((HEALTH_DEADLINE_S + 30))s" 2>&1 || true
    exit 1
  fi
  sleep 2
  waited=$((waited + 2))
done
echo "deploy OK — vires healthy on :${PORT} (after ~${waited}s)"
