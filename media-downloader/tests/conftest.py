from __future__ import annotations

import os
from pathlib import Path

import pytest
import pytest_asyncio

# Ensure a predictable environment for every test regardless of any .env
# file present on the developer's machine.
os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("RUN_EXTERNAL_TESTS", "false")


@pytest_asyncio.fixture
async def fake_redis():
    import fakeredis.aioredis

    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


@pytest.fixture
def tmp_media_dir(tmp_path: Path) -> Path:
    d = tmp_path / "media-downloader"
    d.mkdir()
    return d


@pytest.fixture
def run_external_tests() -> bool:
    return os.environ.get("RUN_EXTERNAL_TESTS", "false").lower() == "true"
