from __future__ import annotations

from pathlib import Path

import pytest

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


class TestForceIpv4:
    def test_disabled_by_default(self, tmp_path):
        adapter = YouTubeAdapter()
        options = DownloadOptions(output_dir=tmp_path, force_ipv4=False)
        opts = adapter._base_ydl_opts(options, Path(tmp_path))

        assert "source_address" not in opts

    def test_sets_source_address_when_enabled(self, tmp_path):
        adapter = YouTubeAdapter()
        options = DownloadOptions(output_dir=tmp_path, force_ipv4=True)
        opts = adapter._base_ydl_opts(options, Path(tmp_path))

        assert opts["source_address"] == "0.0.0.0"


class TestNetworkRobustnessDefaults:
    def test_sets_fragment_retries_and_throttle_detection(self, tmp_path):
        adapter = YouTubeAdapter()
        options = DownloadOptions(output_dir=tmp_path)
        opts = adapter._base_ydl_opts(options, Path(tmp_path))

        assert opts["fragment_retries"] == 10
        assert opts["throttledratelimit"] == 51_200


class TestCodecPreferringFormatStrings:
    @pytest.mark.parametrize("quality", list(QualityMode))
    def test_every_video_preset_prefers_avc1(self, quality, tmp_path):
        adapter = YouTubeAdapter()
        options = DownloadOptions(quality=quality, audio_only=False, output_dir=tmp_path)
        opts = adapter._base_ydl_opts(options, Path(tmp_path))

        assert "vcodec^=avc1" in opts["format"]

    def test_audio_only_format_has_no_codec_filter(self, tmp_path):
        adapter = YouTubeAdapter()
        options = DownloadOptions(audio_only=True, output_dir=tmp_path)
        opts = adapter._base_ydl_opts(options, Path(tmp_path))

        assert opts["format"] == "bestaudio/best"


class TestVcodecPopulatedFromInfo:
    def test_collect_files_reads_vcodec_from_requested_downloads(self, tmp_path):
        adapter = YouTubeAdapter()
        video_path = tmp_path / "abc.mp4"
        video_path.write_bytes(b"fake video bytes")

        info = {
            "id": "abc",
            "title": "Test video",
            "requested_downloads": [
                {"filepath": str(video_path), "vcodec": "vp09.00.10.08"}
            ],
        }
        files = adapter._collect_files(info, tmp_path)

        assert len(files) == 1
        assert files[0].vcodec == "vp09.00.10.08"

    def test_collect_files_falls_back_to_entry_level_vcodec(self, tmp_path):
        adapter = YouTubeAdapter()
        video_path = tmp_path / "abc.mp4"
        video_path.write_bytes(b"fake video bytes")

        info = {
            "id": "abc",
            "title": "Test video",
            "vcodec": "avc1.640028",
            "requested_downloads": [{"filepath": str(video_path)}],
        }
        files = adapter._collect_files(info, tmp_path)

        assert files[0].vcodec == "avc1.640028"
