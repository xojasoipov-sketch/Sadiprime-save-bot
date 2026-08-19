# Infrastructure Audit — media-downloader vs. SadiPrime

## What could and could not be done from this session

This service was built and verified from an **isolated, ephemeral cloud
container** (a Claude Code remote session), not from a shell on your actual
Hetzner server. That container has no SSH access, no credentials, and no
network path to your production host. Concretely:

**Could NOT be done here (must be run by you, on the real server):**
- Live audit of the actual Hetzner box's Docker containers, networks,
  volumes, ports, firewall rules, CPU/RAM/disk.
- Confirmation of SadiPrime's actual container names, images, resource
  usage, or exposed ports.
- Live deployment of media-downloader alongside SadiPrime.
- Post-deploy verification that SadiPrime is "UNCHANGED / HEALTHY" on the
  real host.

**Could be done here, and was:**
- Built the full, isolated codebase (bot, worker, adapters, security,
  tests, Docker).
- Ran the real test suite: **104/104 tests passed**, `ruff check` clean,
  `mypy` clean, against the exact pinned dependencies in
  `requirements.txt`.
- Built the actual Docker image from the actual `Dockerfile` and ran the
  actual `docker-compose.yml` stack (redis + bot + worker) in this
  sandbox. Confirmed: Redis reports `healthy`; the worker reports
  `healthy` and correctly resolves `redis` on the internal Docker network;
  the bot container starts, loads config, and correctly attempts to reach
  `api.telegram.org` (it fails here only because this sandbox's network
  intercepts outbound TLS with its own proxy CA — that constraint is
  specific to this sandbox, not your Hetzner host, and disappears with a
  real `BOT_TOKEN` and normal internet egress).
- Confirmed **zero ports are published to the host** by any service
  (`docker port` returns nothing for all three containers); Redis's port
  is only visible to containers on `media_downloader_network`.

## What you need to do before/after deploying on Hetzner

1. **Before deploying**, SSH into the Hetzner box and run the included,
   read-only audit script:
   ```bash
   ./scripts/audit_server.sh | tee audit-report-$(date +%Y%m%d).txt
   ```
   This lists every running container (including SadiPrime's), all Docker
   networks/volumes, host ports, CPU/RAM/disk, and firewall rules. It makes
   **zero changes**. Review it and confirm nothing in media-downloader's
   compose project (`media-downloader`, network
   `media_downloader_network`, volumes `media_downloader_redis_data` /
   `media_downloader_tmp`, container names `media-downloader-*`) collides
   with anything SadiPrime uses.

2. **Tune the limits** in `.env` (`MAX_CONCURRENT_DOWNLOADS`,
   `MAX_FILE_SIZE_MB`, memory limits in `docker-compose.yml`, etc.) to the
   actual free CPU/RAM/disk headroom the audit reports — the defaults are
   conservative placeholders, not measured values.

3. **Deploy**: `./deploy.sh [sadiprime-compose-project-name]`. Passing
   SadiPrime's compose project name makes the script snapshot SadiPrime's
   container state before deploying and print it again after, so you can
   compare by eye that nothing changed.

4. **Verify**: `./scripts/health_check.sh [sadiprime-compose-project-name]`
   any time afterward — read-only, confirms media-downloader's own health
   and SadiPrime's container status side by side.

## Isolation guarantees built into this service (verifiable in the compose
file and confirmed live in this sandbox)

- Own Docker Compose project (`media-downloader`), own containers
  (`media-downloader-bot`, `-worker`, `-redis`), own network
  (`media_downloader_network`, not shared/external), own volumes
  (`media_downloader_redis_data`, `media_downloader_tmp`).
- No shared database, no shared Redis, no shared application container
  with SadiPrime.
- No ports published to the host or internet — bot uses Telegram long
  polling; Redis is reachable only from the two containers on
  `media_downloader_network`.
- Per-container CPU/memory limits in `docker-compose.yml`, kept
  deliberately bounded so SadiPrime's resources are never starved — tune
  these against your audit's numbers.
- `deploy.sh` and `Makefile` only ever run `docker compose -p
  media-downloader ...` — no broad `docker system prune`, no bare
  `docker compose down` outside this project, nothing that could touch
  SadiPrime's containers/volumes/networks.
