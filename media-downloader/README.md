# media-downloader

An isolated Telegram bot that downloads public media (video/image/audio)
from Instagram, TikTok, YouTube and Pinterest and sends it back to the
user. It can also find music by name: send a song/artist name with no
link and the bot shows up to 10 YouTube results to pick from, then sends
the chosen one as audio (mp3); an `/settings` toggle switches any URL
download to audio-only too. Built to run alongside another production
system (e.g. "SadiPrime")
on the same host **without sharing** its database, Redis, Docker network,
volumes, or application containers. See
[`docs/ARCHITECTURE_AUDIT.md`](docs/ARCHITECTURE_AUDIT.md) for the
isolation guarantees and what was/wasn't possible to verify from a remote
build session vs. what you must verify on your own server.

## Architecture

```
Telegram user
    │  sends a URL
    ▼
bot (aiogram, long polling — no public port)
    │  validates URL (SSRF/domain allowlist), rate-limits, enqueues a job
    ▼
Redis (internal network only — job queue + state + rate limits)
    │
    ▼
worker (bounded concurrency)
    │  downloader/registry.py picks an adapter by domain
    ▼
downloader/{instagram,tiktok,youtube,pinterest}.py  (yt-dlp backed)
    │  writes into TEMP_DIR/<job_id>/
    ▼
media/validator.py (magic-byte signature check, size, path-traversal)
    │
    ▼
Telegram upload (video/photo/audio, or a media group for carousels)
    │
    ▼
media/cleanup.py removes TEMP_DIR/<job_id>/
```

Three containers, one compose project: `bot`, `worker`, `redis`. Redis is
the only datastore — no Postgres/SQLite (see section 28 of the original
spec / `docs/ARCHITECTURE_AUDIT.md`): job state, the queue, rate limits,
and stats are all Redis keys with TTLs.

### Music search (no link needed)

A plain-text message with no URL is treated as a song/artist search. The
flow (`downloader/music_search.py`, `bot/handlers/download.py`,
`bot/handlers/music_pick.py`, `bot/services/search_sessions.py`):

1. The text is sanitized and run as a lightweight (metadata-only, no
   download) `ytsearchN:` query against YouTube — up to 10 results.
2. The bot replies with a numbered list (title + duration) and an inline
   keyboard of number buttons. The candidate list itself is held
   server-side in a short-lived (5 min) Redis session — a Telegram
   `callback_data` is too small (64 bytes) to carry it — keyed by a random
   session id, and checked against the original requester's user id so
   only they can act on their own results.
3. Tapping a number turns that specific result into a normal download job
   (forced audio-only; ffmpeg extracts mp3 regardless of the raw stream's
   container), going through the same `detect_platform()` validation and
   `enqueue_download_job()` limiter path as a pasted URL.

This path is separate from `detect_platform()` / `PLATFORM_DOMAINS` for
the *search* step — it's invoked directly by the bot handler, not
selected by URL domain, and `music_search` is excluded from
`supported_platforms()`. Once a specific video is picked, though, it's
downloaded as a normal `youtube` job.

`/settings` also has an audio-only toggle that, when on, sends *any* URL
download (not just search) as audio.

### Adding a new platform

1. Add its domains to `PLATFORM_DOMAINS` in `core/security.py`.
2. Create `downloader/<platform>.py` subclassing `YtDlpAdapter` (or
   `DownloaderAdapter` directly if it needs a non-yt-dlp backend).
3. Register it in `_ADAPTERS` in `downloader/registry.py`.

Nothing in `bot/` or `worker/` needs to change.

## Supported platforms

| Platform  | Domains |
|-----------|---------|
| Instagram | instagram.com |
| TikTok    | tiktok.com, vm.tiktok.com, vt.tiktok.com, m.tiktok.com |
| YouTube   | youtube.com, youtu.be, m.youtube.com, music.youtube.com |
| Pinterest | pinterest.com, pin.it, and a few regional pinterest.\* TLDs |

Only public content. No login, no cookies, no private-account or DRM
bypass — see "Compliance" below.

## Installation

Requires Docker + Docker Compose. Nothing is installed globally on the
host — everything runs in containers.

```bash
cp .env.example .env
# edit .env: set BOT_TOKEN (from @BotFather), ADMIN_USER_IDS, and tune
# the limits to your server's actual free capacity (see docs/ARCHITECTURE_AUDIT.md)

./deploy.sh                      # or: ./deploy.sh <sadiprime-compose-project-name>
```

`deploy.sh` validates `.env`, builds, starts the stack, polls health for
up to 60s, and prints logs if startup fails. It only ever touches the
`media-downloader` compose project.

## Configuration (`.env`)

See `.env.example` for the full, commented list. Key ones:

| Variable | Meaning |
|---|---|
| `BOT_TOKEN` | Telegram bot token. Never commit this. |
| `ADMIN_USER_IDS` | Comma-separated Telegram user IDs allowed to run `/status` and `/stats`. |
| `REDIS_URL` | Internal Redis URL — leave as `redis://redis:6379/0`. |
| `DEFAULT_LANGUAGE` | `uz` (default) or `en`. |
| `MAX_CONCURRENT_DOWNLOADS` | Global worker concurrency. |
| `MAX_USER_CONCURRENT_JOBS` / `MAX_ACTIVE_JOBS_PER_USER` | Per-user concurrent job cap. |
| `MAX_DAILY_JOBS_PER_USER` | Per-user daily quota. |
| `MAX_FILE_SIZE_MB` | Reject files above this size. |
| `MIN_FREE_DISK_MB` | Refuse new jobs if host disk drops below this. |
| `MAX_TEMP_STORAGE_MB` | Hard cap on total bytes media-downloader holds in `TEMP_DIR`. |
| `DOWNLOAD_TIMEOUT_SECONDS` / `PROCESSING_TIMEOUT_SECONDS` / `UPLOAD_TIMEOUT_SECONDS` / `JOB_TIMEOUT_SECONDS` | Per-stage and overall timeouts. |
| `JOB_LEASE_SECONDS` | Heartbeat lease TTL for crash recovery. |
| `MAX_REQUESTS_PER_MINUTE` | Per-user rate limit (Redis-backed). |
| `DEFAULT_QUALITY` | `LOW` / `MEDIUM` / `HIGH` / `BEST_COMPATIBLE`. |
| `ENABLE_COMPRESSION_FALLBACK` | Local ffmpeg fallbacks before failing outright: fix an incompatible video codec, and/or fit an oversized video under `MAX_FILE_SIZE_MB`. Default `true`. |
| `FORCE_IPV4` | Force outbound requests over IPv4. Only useful on a host with a flaky IPv6 route to a platform's CDN. Default `false`. |
| `COOKIES_FILE` | Optional path to a cookies.txt for authenticated requests. See below. |

**Set these from your own server's actual free CPU/RAM/disk** — the
defaults are conservative placeholders, not a promise the host can handle
them. Run `scripts/audit_server.sh` first.

## Instagram cookies (optional)

Instagram has been increasingly rejecting anonymous requests, even for
genuinely public reels/posts — you'll see this in `worker` logs as
`Requested content is not available, rate-limit reached or login
required`. This isn't a bug in this codebase; it's yt-dlp hitting
Instagram's own anti-bot wall, and yt-dlp's own documented fix is to
authenticate as a real account via cookies. TikTok/YouTube/Pinterest
don't need this.

1. **Use a dedicated Instagram account you control for this — not your
   personal one.** The cookies file is equivalent to that account's
   password: anyone who gets it can act as that account. This is normal
   login, not an access-control bypass — it's how any regular user would
   view the same content, and this project does not use it to reach
   private accounts or content the account itself couldn't otherwise see.
2. Log into that account in a desktop browser, then export cookies for
   `instagram.com` in Netscape format with a browser extension (e.g. "Get
   cookies.txt LOCALLY" for Chrome/Firefox).
3. Put the exported file at `media-downloader/secrets/cookies.txt` on
   your server (`chmod 644` so the container's non-root user can read it;
   never commit it — `.gitignore` already excludes everything under
   `secrets/` except this README and `.gitkeep`).
4. In `.env`, uncomment: `COOKIES_FILE=/app/secrets/cookies.txt`
5. Redeploy: `docker compose -p media-downloader up -d --force-recreate`

If the session expires (the account gets logged out anywhere, 2FA
re-prompts, etc.), re-export and repeat steps 2–3; no code changes
needed.

## Download reliability

Beyond cookies, a few things specifically target Instagram/TikTok's
tendency to be flakier than YouTube/Pinterest:

- **Keep yt-dlp current.** `requirements.txt` pins an exact version —
  yt-dlp ships frequent point releases specifically to patch broken
  Instagram/TikTok extractors as those platforms change their internals.
  A stale pin is a common, silent cause of downloads that used to work
  suddenly failing. Check [PyPI](https://pypi.org/project/yt-dlp/) or
  `pip index versions yt-dlp` periodically and bump the pin; there's no
  automated check for this yet (see "Remaining limitations").
- **Codec-compatibility fallback.** Instagram/TikTok sometimes serve
  VP9-in-mp4, which passes our format filters but won't autoplay inline
  in Telegram's iOS client. Every quality preset now prefers an
  avc1/h264 stream at the yt-dlp level first
  (`downloader/_ytdlp_common.py`); if none is offered, `media/processor.py`
  re-encodes to H.264 after the fact (audio untouched). Same
  `ENABLE_COMPRESSION_FALLBACK` switch as the oversized-file fallback.
- **Network robustness.** `fragment_retries` (segmented/HLS delivery,
  common on IG reels/stories) and throttle detection
  (`throttledratelimit`) are always on — the yt-dlp Python API doesn't
  default these the way its CLI does, so they're set explicitly. `FORCE_IPV4`
  is available if you're seeing connection issues that look like a flaky
  IPv6 route to a platform's CDN on your specific host.
- **Proactive admin alerts.** A non-retryable (or retry-exhausted) job
  failure now DMs every `ADMIN_USER_IDS` with the platform, error type,
  and URL — deduplicated per (platform, error type) with a 10-minute
  cooldown, so an outage (e.g. Instagram cookies expiring) sends one
  alert, not one per failed job, and you don't have to poll `/status` to
  notice.

## Docker commands

All commands are scoped to this project only — they never touch anything
outside `docker compose -p media-downloader`.

```bash
make up          # build + start
make down        # stop and remove this project's containers
make logs        # follow all logs
make logs-bot    # bot only
make logs-worker # worker only
make status      # container + redis health
make uninstall   # stop and remove this project's containers, network, volumes
```

## Telegram bot setup

1. Create a bot with [@BotFather](https://t.me/BotFather), copy the token
   into `.env` as `BOT_TOKEN`.
2. Get your numeric Telegram user ID (e.g. via @userinfobot) and put it in
   `ADMIN_USER_IDS` to use `/status` (live infra health) and `/stats`
   (lifetime job totals, success rate, per-platform breakdown).
3. Long polling is used by default — no public port, no domain, no HTTPS
   certificate needed. Webhook mode can be added later by changing
   `bot/main.py`'s startup (swap `start_polling` for a webhook handler);
   nothing else in the codebase depends on the transport.

## Limits & resource protection

- Global + per-user concurrency limits, per-user rate limiting and daily
  quotas (all Redis-backed, see `core/limits.py`).
- Disk-space checks before every job (`worker/services/disk.py`): refuses
  new jobs if free disk or the temp-storage cap would be exceeded.
- Docker `deploy.resources.limits` (CPU/memory) per container in
  `docker-compose.yml` — the worker (the resource-hungry piece) is bounded
  well below typical host capacity by default; tune to your audit.
- Per-job, per-processing, per-upload, and overall job timeouts.
- Every job's temp directory (`TEMP_DIR/<job_id>/`) is deleted on success,
  failure, and timeout, plus a periodic orphan sweep recovers anything left
  behind by a worker crash.

## Security

- **SSRF protection** (`core/security.py`): scheme allowlist (http/https
  only), rejects localhost/loopback/private/link-local/reserved IPs and
  literal IP addresses, resolves hostnames and blocks anything pointing at
  a private address, domain allowlist per platform.
- **File validation** (`media/validator.py`): real magic-byte signature
  check (never trusts the extension or yt-dlp's reported type), path-
  traversal guard (every produced file must resolve inside its job
  directory), size limits, crude decompression-bomb / absurd-dimension
  guard.
- **Filename sanitization**: every filename is stripped of path separators
  and traversal sequences before use.
- **Never executes downloaded files.**
- **Secrets**: `BOT_TOKEN` only ever comes from the environment; the
  structured logger redacts token-shaped keys; `.env` is gitignored.
- **Rate limiting**: per-user requests/minute, concurrent jobs, and daily
  quota, all enforced in Redis before a job is created.

## Error handling & retries

Errors are typed (`downloader/base.py`): `UnsupportedPlatformError`,
`PrivateContentError`, `MediaUnavailableError`, `DownloadTimeoutError`,
`FileTooLargeError`, `DiskSpaceError`, `RateLimitedByPlatformError`,
`TelegramUploadError`, `ProcessingError`, plus
`core.security.InvalidUrlError` and `media.validator.FileValidationError`.
Each maps to a friendly, translated user message — no stack traces ever
reach the user. Only errors marked `retryable = True` (timeouts, platform
rate limiting, transient Telegram upload errors) are retried, up to 3
attempts total with exponential backoff.

## Crash recovery

Each in-progress job holds a Redis lease renewed by a heartbeat; if a
worker crashes, the lease expires and a periodic sweep
(`ORPHAN_CLEANUP_INTERVAL_SECONDS`) marks the job `FAILED` and cleans its
temp directory. A second sweep removes any orphaned temp directories older
than `ORPHAN_MAX_AGE_SECONDS`. The queue itself is a Redis list, so a
worker restart never loses queued (not-yet-started) jobs.

## Testing

```bash
make install-dev
make lint        # ruff
make typecheck    # mypy
make test         # pytest — 209 tests, all mocked, no network access
```

The normal suite never touches Instagram/TikTok/YouTube/Pinterest or a
real Telegram bot — everything external is faked (`fakeredis`, adapter/Bot
doubles). Set `RUN_EXTERNAL_TESTS=true` to opt into tests that would hit
live platforms (none are currently implemented; the flag exists per the
project's testing policy for anyone adding them later).

Coverage: URL parsing & normalization, SSRF protection, domain allowlist,
platform detection/adapter selection, filename sanitization, rate
limiting (per-minute, per-user active jobs, daily quota, queue capacity),
job lifecycle (create/dequeue/save/get), lease-based crash recovery,
job-dir and orphan cleanup, file signature/path-traversal/size validation,
i18n message catalog parity, the full error taxonomy →
user-message mapping, retry vs. no-retry behavior, and an end-to-end
worker-pipeline integration test (success path, retryable-then-succeeds,
non-retryable-fails-immediately, and user quality/audio-only preferences
correctly reaching `DownloadOptions`), music-search query sanitization and
result parsing, the audio-only ffmpeg-postprocessor wiring, the full
bot-layer search → results-list → pick → enqueue flow (including the
Redis-backed search-session store, its per-requester authorization check,
and its 5-minute TTL), cookies-file and force-IPv4 wiring, the
codec-preferring format strings, the oversized-video/incompatible-codec
compression-fallback decision logic (and its on/off setting gate,
including their interaction — a codec fix followed by a still-needed
size fix), `/stats`'s per-platform breakdown, and the cooldown-deduplicated
proactive admin-alerting logic.

## Troubleshooting

- **Bot doesn't respond**: `make logs-bot`. Check `BOT_TOKEN` is correct
  and the container has internet egress (Telegram long polling needs
  outbound HTTPS to `api.telegram.org`).
- **Jobs stay queued**: `make logs-worker`; check `docker compose -p
  media-downloader ps` for the worker's health; `/status` (as an admin)
  shows queue size and worker health.
- **"Media too large"**: raise `MAX_FILE_SIZE_MB` if your server and
  Telegram's limits allow it, or lower `DEFAULT_QUALITY`.
- **Disk errors**: check `MIN_FREE_DISK_MB` / `MAX_TEMP_STORAGE_MB` against
  actual free space; `make status` and `/status` both report free disk.

## Backup / rollback

There is no persistent user data by default (media is deleted after every
job; Redis holds only transient queue/rate-limit state you can safely
lose). To remove the service entirely without touching anything else on
the host:

```bash
make uninstall   # docker compose -p media-downloader down -v
```

This only ever removes `media-downloader`'s own containers, network, and
volumes.

## Compliance

This service downloads content the user is presumably authorized to
access and save. It does not implement DRM bypass, authentication bypass,
private-account bypass, CAPTCHA circumvention, or any other access-control
circumvention, and is not designed to evade platform restrictions. Respect
the source platforms' terms of service and applicable copyright law.

## Remaining limitations

- **Live server audit / deployment verification**: not performed by this
  codebase — see `docs/ARCHITECTURE_AUDIT.md` for exactly what was and
  wasn't verifiable from the build environment, and the scripts you should
  run on the actual Hetzner host.
- **Webhook mode**: not implemented (long polling only); documented as an
  extension point.
- **Web/admin dashboard**: intentionally out of scope for v1 (Telegram
  admin commands only), per the original spec.
- **Integration tests against live platforms**: the `RUN_EXTERNAL_TESTS`
  flag and policy exist, but no live-platform tests are implemented yet —
  platform APIs/pages change over time and would need periodic upkeep.
- **ffmpeg fallback re-encode paths** (`media/processor.py`, both the
  size-fix and codec-fix): wired into the pipeline and unit-tested with a
  mocked ffmpeg call, but not exercised against a real oversized/VP9
  video end-to-end in this session (would require a live download that
  actually triggers one).
- **No automated yt-dlp-staleness check**: README "Download reliability"
  documents checking PyPI manually; nothing in the bot itself surfaces
  "yt-dlp is N releases behind" (e.g. in `/status`). Worth adding if
  extractor breakage becomes a recurring issue.
