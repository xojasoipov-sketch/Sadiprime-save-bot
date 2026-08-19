#!/usr/bin/env bash
# Deploys ONLY the media-downloader stack. Every command is scoped with
# `-p media-downloader`. This script never touches any other compose
# project, never runs `docker system prune`, never removes volumes or
# networks it doesn't own, and never restarts anything outside this
# project.
#
# Usage: ./deploy.sh [sadiprime-compose-project-name]

set -euo pipefail

cd "$(dirname "$0")"

SADIPRIME_PROJECT="${1:-}"
COMPOSE="docker compose -p media-downloader"

echo "== Step 1/5: validate configuration =="
if [ ! -f .env ]; then
  echo "ERROR: .env not found. Copy .env.example to .env and fill in BOT_TOKEN first." >&2
  exit 1
fi
if ! grep -qE '^BOT_TOKEN=.+' .env; then
  echo "ERROR: BOT_TOKEN is not set in .env." >&2
  exit 1
fi
echo "OK: .env present and BOT_TOKEN is set."

if [ -n "$SADIPRIME_PROJECT" ]; then
  echo
  echo "== Pre-deploy SadiPrime snapshot (project: $SADIPRIME_PROJECT) =="
  docker compose -p "$SADIPRIME_PROJECT" ps || echo "WARNING: could not read SadiPrime project state"
fi

echo
echo "== Step 2/5: build images =="
$COMPOSE build

echo
echo "== Step 3/5: start the stack =="
$COMPOSE up -d

echo
echo "== Step 4/5: verify health (up to 60s) =="
ok=false
for _ in $(seq 1 12); do
  sleep 5
  bot_status=$(docker inspect --format='{{.State.Health.Status}}' media-downloader-bot 2>/dev/null || echo "starting")
  worker_status=$(docker inspect --format='{{.State.Health.Status}}' media-downloader-worker 2>/dev/null || echo "starting")
  redis_status=$(docker inspect --format='{{.State.Health.Status}}' media-downloader-redis 2>/dev/null || echo "starting")
  echo "bot=$bot_status worker=$worker_status redis=$redis_status"
  if [ "$bot_status" = "healthy" ] && [ "$worker_status" = "healthy" ] && [ "$redis_status" = "healthy" ]; then
    ok=true
    break
  fi
done

if [ "$ok" != "true" ]; then
  echo
  echo "== Step 5/5: startup failed — showing recent logs =="
  $COMPOSE logs --tail=100
  exit 1
fi

echo
echo "== Step 5/5: media-downloader is up and healthy =="
$COMPOSE ps

if [ -n "$SADIPRIME_PROJECT" ]; then
  echo
  echo "== Post-deploy SadiPrime verification (project: $SADIPRIME_PROJECT) =="
  docker compose -p "$SADIPRIME_PROJECT" ps
  echo "Compare against the pre-deploy snapshot above — it must be unchanged."
else
  echo
  echo "NOTE: pass the SadiPrime compose project name as an argument to this"
  echo "script to automatically snapshot/verify it before and after deploy."
fi
