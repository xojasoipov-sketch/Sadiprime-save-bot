#!/usr/bin/env bash
# Read-only Hetzner/Docker audit. Makes ZERO changes to the host.
# Run this on the actual production server BEFORE deploying media-downloader,
# to confirm what SadiPrime is running and how much headroom is available.
#
# Usage: ./scripts/audit_server.sh | tee audit-report-$(date +%Y%m%d-%H%M%S).txt

set -euo pipefail

section() { echo; echo "=== $1 ==="; }

section "Host resources"
echo "--- CPU ---"
nproc --all 2>/dev/null || true
echo "--- Memory ---"
free -h 2>/dev/null || true
echo "--- Disk ---"
df -h 2>/dev/null || true

section "Docker version"
docker version 2>/dev/null || echo "docker not available / insufficient permissions"

section "All running containers (any project)"
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null || true

section "All containers, including stopped"
docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}' 2>/dev/null || true

section "Docker Compose projects (from container labels)"
docker ps -a --format '{{.Label "com.docker.compose.project"}}' 2>/dev/null | sort -u | grep -v '^$' || true

section "Docker networks"
docker network ls 2>/dev/null || true

section "Docker volumes"
docker volume ls 2>/dev/null || true

section "Exposed ports (host bindings across all containers)"
docker ps --format '{{.Names}}: {{.Ports}}' 2>/dev/null || true

section "Per-container resource usage (live snapshot)"
docker stats --no-stream 2>/dev/null || true

section "Reverse proxy check (common patterns)"
docker ps --format '{{.Names}} {{.Image}}' 2>/dev/null | grep -iE 'nginx|traefik|caddy' || echo "No obvious reverse-proxy container name matched"

section "Host firewall (read-only)"
if command -v ufw >/dev/null 2>&1; then
  ufw status verbose 2>/dev/null || echo "ufw present but status unreadable (needs sudo)"
else
  echo "ufw not installed; checking iptables (may require sudo)"
  iptables -L -n 2>/dev/null | head -50 || echo "iptables not readable without elevated privileges"
fi

section "Listening ports on host"
ss -tulpn 2>/dev/null || netstat -tulpn 2>/dev/null || echo "ss/netstat not available"

echo
echo "=== Audit complete ==="
echo "This script made NO changes. Review the SadiPrime containers/networks/"
echo "volumes/ports above, then confirm media-downloader's compose project"
echo "('media-downloader', network 'media_downloader_network', volumes"
echo "'media_downloader_redis_data' / 'media_downloader_tmp') does not collide"
echo "with anything listed."
