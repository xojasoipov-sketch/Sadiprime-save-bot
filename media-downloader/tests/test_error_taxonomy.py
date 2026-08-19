from __future__ import annotations

from core.security import InvalidUrlError as SecurityInvalidUrlError
from downloader.base import (
    BotDetectionError,
    DiskSpaceError,
    DownloadTimeoutError,
    FileTooLargeError,
    MediaUnavailableError,
    PrivateContentError,
    RateLimitedByPlatformError,
    TelegramUploadError,
    UnsupportedPlatformError,
)
from media.validator import FileValidationError
from worker.tasks.download import _error_key


class TestRetryability:
    def test_transient_errors_are_retryable(self):
        assert DownloadTimeoutError("x").retryable is True
        assert RateLimitedByPlatformError("x").retryable is True
        assert TelegramUploadError("x").retryable is True
        assert BotDetectionError("x").retryable is True

    def test_permanent_errors_are_not_retryable(self):
        assert PrivateContentError("x").retryable is False
        assert UnsupportedPlatformError("x").retryable is False
        assert FileTooLargeError("x").retryable is False
        assert MediaUnavailableError("x").retryable is False


class TestErrorToMessageMapping:
    def test_private_content_maps_to_private_key(self):
        assert _error_key(PrivateContentError("x")) == "error_private"

    def test_bot_detection_maps_to_its_own_key_not_private(self):
        # Must not be lumped in with error_private: the video isn't
        # actually private, YouTube just flagged the request itself.
        assert _error_key(BotDetectionError("x")) == "error_bot_check"

    def test_too_large_maps_correctly(self):
        assert _error_key(FileTooLargeError("x")) == "error_too_large"

    def test_timeout_maps_correctly(self):
        assert _error_key(DownloadTimeoutError("x")) == "error_timeout"

    def test_disk_space_maps_to_generic(self):
        assert _error_key(DiskSpaceError("x")) == "error_generic"

    def test_rate_limited_by_platform_maps_correctly(self):
        assert _error_key(RateLimitedByPlatformError("x")) == "error_rate_limited"

    def test_unavailable_maps_to_download_failed(self):
        assert _error_key(MediaUnavailableError("x")) == "error_download_failed"

    def test_unsupported_platform_maps_correctly(self):
        assert _error_key(UnsupportedPlatformError("x")) == "error_unsupported_link"

    def test_invalid_url_maps_correctly(self):
        assert _error_key(SecurityInvalidUrlError("x")) == "error_invalid_url"

    def test_file_validation_error_maps_to_download_failed(self):
        assert _error_key(FileValidationError("x")) == "error_download_failed"

    def test_unknown_exception_maps_to_generic(self):
        assert _error_key(RuntimeError("something unexpected")) == "error_generic"
