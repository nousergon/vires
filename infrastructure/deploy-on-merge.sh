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
DIST_S3="s3://alpha-engine-research/infrastructure/vires/web-dist.tgz"
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

# --- restart + health check ------------------------------------------------- #
sudo systemctl restart vires
sleep 4
curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null || { echo "vires health FAILED"; exit 1; }
echo "deploy OK — vires healthy on :${PORT}"
