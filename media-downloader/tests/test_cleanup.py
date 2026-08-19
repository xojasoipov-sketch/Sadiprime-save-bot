from __future__ import annotations

import os
import time

from media.cleanup import cleanup_job_dir, job_dir_for, sweep_orphaned_dirs, total_temp_usage_bytes


class TestJobDirCleanup:
    def test_removes_existing_job_dir(self, tmp_media_dir):
        job_id = "abc123"
        job_dir = job_dir_for(tmp_media_dir, job_id)
        job_dir.mkdir(parents=True)
        (job_dir / "file.mp4").write_bytes(b"data")

        cleanup_job_dir(tmp_media_dir, job_id)

        assert not job_dir.exists()

    def test_noop_when_dir_missing(self, tmp_media_dir):
        cleanup_job_dir(tmp_media_dir, "never-existed")  # should not raise

    def test_job_id_is_sanitized(self, tmp_media_dir):
        # job_id containing traversal characters must not escape temp_dir.
        malicious_id = "../../etc"
        path = job_dir_for(tmp_media_dir, malicious_id)
        assert tmp_media_dir in path.parents


class TestOrphanSweep:
    def test_removes_dirs_older_than_max_age(self, tmp_media_dir):
        old_dir = tmp_media_dir / "old-job"
        old_dir.mkdir()
        old_time = time.time() - 3600
        os.utime(old_dir, (old_time, old_time))

        removed = sweep_orphaned_dirs(tmp_media_dir, max_age_seconds=1800)

        assert removed == 1
        assert not old_dir.exists()

    def test_keeps_recent_dirs(self, tmp_media_dir):
        recent_dir = tmp_media_dir / "recent-job"
        recent_dir.mkdir()

        removed = sweep_orphaned_dirs(tmp_media_dir, max_age_seconds=1800)

        assert removed == 0
        assert recent_dir.exists()

    def test_missing_temp_dir_is_a_noop(self, tmp_path):
        missing = tmp_path / "does-not-exist"
        assert sweep_orphaned_dirs(missing, max_age_seconds=60) == 0


class TestTempUsage:
    def test_sums_file_sizes_recursively(self, tmp_media_dir):
        job_dir = tmp_media_dir / "job-1"
        job_dir.mkdir()
        (job_dir / "a.mp4").write_bytes(b"x" * 100)
        (job_dir / "b.mp4").write_bytes(b"y" * 50)

        assert total_temp_usage_bytes(tmp_media_dir) == 150

    def test_zero_for_empty_dir(self, tmp_media_dir):
        assert total_temp_usage_bytes(tmp_media_dir) == 0
