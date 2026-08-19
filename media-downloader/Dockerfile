# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm AS base

# ffmpeg is required for the rare re-encode fallback (media/processor.py);
# ca-certificates for TLS to the platform CDNs; procps provides pgrep,
# used by the bot service's healthcheck (docker-compose.yml).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates curl procps \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 10001 downloader \
    && useradd --uid 10001 --gid downloader --shell /usr/sbin/nologin --create-home downloader

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /tmp/media-downloader && chown -R downloader:downloader /app /tmp/media-downloader

USER downloader

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Default entrypoint runs the bot; docker-compose overrides `command` for
# the worker service. No ports are exposed — Telegram long polling only.
CMD ["python", "-m", "bot.main"]
