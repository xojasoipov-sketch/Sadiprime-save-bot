"""Central configuration, loaded from environment variables / .env.

All tunables that affect resource usage on the shared Hetzner host live
here so operators can adjust them without touching code.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class QualityMode(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    BEST_COMPATIBLE = "BEST_COMPATIBLE"


class Language(str, Enum):
    UZ = "uz"
    EN = "en"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Telegram ---------------------------------------------------
    bot_token: str = Field(default="", alias="BOT_TOKEN")
    admin_user_ids_raw: str = Field(default="", alias="ADMIN_USER_IDS")

    # --- Redis --------------------------------------------------------
    redis_url: str = Field(default="redis://redis:6379/0", alias="REDIS_URL")

    # --- Language -----------------------------------------------------
    default_language: Language = Field(default=Language.UZ, alias="DEFAULT_LANGUAGE")

    # --- Concurrency & queue -------------------------------------------
    max_concurrent_downloads: int = Field(default=2, alias="MAX_CONCURRENT_DOWNLOADS", ge=1, le=16)
    max_user_concurrent_jobs: int = Field(default=1, alias="MAX_USER_CONCURRENT_JOBS", ge=1, le=8)
    max_active_jobs_per_user: int = Field(default=1, alias="MAX_ACTIVE_JOBS_PER_USER", ge=1, le=8)
    max_daily_jobs_per_user: int = Field(default=50, alias="MAX_DAILY_JOBS_PER_USER", ge=1)
    max_queue_size: int = Field(default=100, alias="MAX_QUEUE_SIZE", ge=1)

    # --- Files / disk ---------------------------------------------------
    max_file_size_mb: int = Field(default=200, alias="MAX_FILE_SIZE_MB", ge=1, le=2000)
    min_free_disk_mb: int = Field(default=1024, alias="MIN_FREE_DISK_MB", ge=64)
    max_temp_storage_mb: int = Field(default=2048, alias="MAX_TEMP_STORAGE_MB", ge=64)

    # --- Timeouts ---------------------------------------------------------
    download_timeout_seconds: int = Field(default=180, alias="DOWNLOAD_TIMEOUT_SECONDS", ge=5)
    processing_timeout_seconds: int = Field(default=60, alias="PROCESSING_TIMEOUT_SECONDS", ge=5)
    upload_timeout_seconds: int = Field(default=120, alias="UPLOAD_TIMEOUT_SECONDS", ge=5)
    job_timeout_seconds: int = Field(default=300, alias="JOB_TIMEOUT_SECONDS", ge=10)

    job_lease_seconds: int = Field(default=120, alias="JOB_LEASE_SECONDS", ge=10)
    orphan_cleanup_interval_seconds: int = Field(default=300, alias="ORPHAN_CLEANUP_INTERVAL_SECONDS", ge=30)
    orphan_max_age_seconds: int = Field(default=1800, alias="ORPHAN_MAX_AGE_SECONDS", ge=60)

    # --- Rate limiting ----------------------------------------------------
    max_requests_per_minute: int = Field(default=10, alias="MAX_REQUESTS_PER_MINUTE", ge=1)

    # --- Storage ------------------------------------------------------------
    temp_dir: Path = Field(default=Path("/tmp/media-downloader"), alias="TEMP_DIR")

    # --- Quality --------------------------------------------------------------
    default_quality: QualityMode = Field(default=QualityMode.BEST_COMPATIBLE, alias="DEFAULT_QUALITY")

    # --- Optional platform authentication -------------------------------
    # Netscape-format cookies.txt path (yt-dlp's `cookiefile`). Some
    # platforms (notably Instagram) increasingly reject anonymous
    # requests; this is how an operator opts in to authenticating as a
    # real account they control. Unset by default — every adapter must
    # keep working without it for platforms that don't need it. See
    # README.md "Instagram cookies (optional)".
    cookies_file: Path | None = Field(default=None, alias="COOKIES_FILE")

    # --- Logging -----------------------------------------------------------
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # --- Testing -------------------------------------------------------------
    run_external_tests: bool = Field(default=False, alias="RUN_EXTERNAL_TESTS")

    @field_validator("admin_user_ids_raw")
    @classmethod
    def _noop(cls, v: str) -> str:
        return v

    @property
    def admin_user_ids(self) -> set[int]:
        ids: set[int] = set()
        for part in self.admin_user_ids_raw.split(","):
            part = part.strip()
            if part.isdigit():
                ids.add(int(part))
        return ids

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_user_ids


def get_settings() -> Settings:
    """Return a fresh Settings instance.

    Not cached at module import time so tests can construct Settings with
    overridden environment variables freely.
    """

    return Settings()
