from __future__ import annotations

from pathlib import Path

from core.config import QualityMode
from downloader.base import DownloadOptions
from downloader.youtube import YouTubeAdapter


class TestAudioOnlyPostprocessing:
    def test_audio_only_adds_mp3_extraction_postprocessor(self, tmp_path):
        adapter = YouTubeAdapter()
        options = DownloadOptions(
            quality=QualityMode.BEST_COMPATIBLE, audio_only=True, output_dir=tmp_path
        )
        opts = adapter._base_ydl_opts(options, Path(tmp_path))

        assert opts.get("postprocessors")
        pp = opts["postprocessors"][0]
        assert pp["key"] == "FFmpegExtractAudio"
        assert pp["preferredcodec"] == "mp3"

    def test_video_download_has_no_audio_postprocessor(self, tmp_path):
        adapter = YouTubeAdapter()
        options = DownloadOptions(
            quality=QualityMode.BEST_COMPATIBLE, audio_only=False, output_dir=tmp_path
        )
        opts = adapter._base_ydl_opts(options, Path(tmp_path))

        assert "postprocessors" not in opts

    def test_audio_only_format_prefers_bestaudio(self, tmp_path):
        adapter = YouTubeAdapter()
        options = DownloadOptions(
            quality=QualityMode.HIGH, audio_only=True, output_dir=tmp_path
        )
        opts = adapter._base_ydl_opts(options, Path(tmp_path))

        assert opts["format"] == "bestaudio/best"


class TestCookiesFile:
    def test_unset_cookies_file_is_not_passed_to_ytdlp(self, tmp_path):
        adapter = YouTubeAdapter()
        options = DownloadOptions(output_dir=tmp_path, cookies_file=None)
        opts = adapter._base_ydl_opts(options, Path(tmp_path))

        assert "cookiefile" not in opts

    def test_nonexistent_cookies_file_is_not_passed_to_ytdlp(self, tmp_path):
        adapter = YouTubeAdapter()
        options = DownloadOptions(output_dir=tmp_path, cookies_file=tmp_path / "missing.txt")
        opts = adapter._base_ydl_opts(options, Path(tmp_path))

        assert "cookiefile" not in opts

    def test_existing_cookies_file_is_passed_to_ytdlp(self, tmp_path):
        cookies = tmp_path / "cookies.txt"
        cookies.write_text("# Netscape HTTP Cookie File\n")

        adapter = YouTubeAdapter()
        options = DownloadOptions(output_dir=tmp_path, cookies_file=cookies)
        opts = adapter._base_ydl_opts(options, Path(tmp_path))

        assert opts["cookiefile"] == str(cookies)
