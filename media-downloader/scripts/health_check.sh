#!/usr/bin/env bash
# Post-deploy smoke check: confirms media-downloader's own containers are
# healthy AND that SadiPrime's containers are still running/unaffected.
# Read-only — never stops, restarts, or removes anything.
#
# Usage: ./scripts/health_check.sh [sadiprime-compose-project-name]

set -euo pipefail

SADIPRIME_PROJECT="${1:-}"

echo "=== media-downloader containers ==="
docker compose -p media-downloader ps

echo
echo "=== media-downloader health status ==="
for c in media-downloader-bot media-downloader-worker media-downloader-redis; do
  status=$(docker inspect --format='{{.State.Health.Status}}' "$c" 2>/dev/null || echo "no-healthcheck")
  echo "$c: $status"
done

if [ -n "$SADIPRIME_PROJECT" ]; then
  echo
  echo "=== SadiPrime containers (project: $SADIPRIME_PROJECT) — verifying UNCHANGED/HEALTHY ==="
  docker compose -p "$SADIPRIME_PROJECT" ps
else
  echo
  echo "=== All other running containers (verify SadiPrime is still healthy) ==="
  docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}' | grep -v 'media-downloader' || true
  echo "(pass the SadiPrime compose project name as \$1 to check it precisely)"
fi
