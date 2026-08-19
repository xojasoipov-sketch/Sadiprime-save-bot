from __future__ import annotations

from worker.services.job_store import Job, JobStatus, JobStore


def make_job(**overrides) -> Job:
    defaults = {
        "job_id": JobStore.new_job_id(),
        "user_id": 1,
        "chat_id": 1,
        "url": "https://www.instagram.com/reel/x/",
        "platform": "instagram",
    }
    defaults.update(overrides)
    return Job(**defaults)


class TestJobSerialization:
    def test_round_trips_through_json(self):
        job = make_job(status=JobStatus.DOWNLOADING, error="boom")
        restored = Job.from_json(job.to_json())
        assert restored == job

    def test_audio_only_defaults_false(self):
        job = make_job()
        assert job.audio_only is False

    def test_audio_only_round_trips_through_json(self):
        job = make_job(audio_only=True, platform="music_search", url="ytsearch1:test song")
        restored = Job.from_json(job.to_json())
        assert restored.audio_only is True


class TestJobLifecycle:
    async def test_create_enqueues_and_dequeues(self, fake_redis):
        store = JobStore(fake_redis)
        job = make_job()
        await store.create(job)

        assert await store.queue_size() == 1
        dequeued_id = await store.dequeue(timeout_seconds=1)
        assert dequeued_id == job.job_id
        assert await store.queue_size() == 0

    async def test_get_returns_saved_job(self, fake_redis):
        store = JobStore(fake_redis)
        job = make_job()
        await store.create(job)

        fetched = await store.get(job.job_id)
        assert fetched is not None
        assert fetched.job_id == job.job_id
        assert fetched.status == JobStatus.QUEUED

    async def test_get_missing_job_returns_none(self, fake_redis):
        store = JobStore(fake_redis)
        assert await store.get("does-not-exist") is None

    async def test_save_updates_status(self, fake_redis):
        store = JobStore(fake_redis)
        job = make_job()
        await store.create(job)

        job.status = JobStatus.COMPLETED
        await store.save(job)

        fetched = await store.get(job.job_id)
        assert fetched.status == JobStatus.COMPLETED

    async def test_dequeue_times_out_on_empty_queue(self, fake_redis):
        store = JobStore(fake_redis)
        result = await store.dequeue(timeout_seconds=1)
        assert result is None


class TestLeaseRecovery:
    async def test_stale_job_detected_when_lease_expired(self, fake_redis):
        store = JobStore(fake_redis)
        job = make_job(status=JobStatus.DOWNLOADING)
        await store.save(job)
        # No lease acquired -> immediately stale.
        stale = await store.scan_stale_jobs()
        assert [j.job_id for j in stale] == [job.job_id]

    async def test_job_with_live_lease_is_not_stale(self, fake_redis):
        store = JobStore(fake_redis)
        job = make_job(status=JobStatus.DOWNLOADING)
        await store.save(job)
        await store.acquire_lease(job.job_id, ttl_seconds=60)

        stale = await store.scan_stale_jobs()
        assert stale == []

    async def test_queued_job_is_never_considered_stale(self, fake_redis):
        store = JobStore(fake_redis)
        job = make_job(status=JobStatus.QUEUED)
        await store.save(job)

        stale = await store.scan_stale_jobs()
        assert stale == []

    async def test_release_lease_removes_it(self, fake_redis):
        store = JobStore(fake_redis)
        job = make_job()
        await store.acquire_lease(job.job_id, ttl_seconds=60)
        assert await store.lease_alive(job.job_id)
        await store.release_lease(job.job_id)
        assert not await store.lease_alive(job.job_id)


class TestStats:
    async def test_record_completion_updates_counters(self, fake_redis):
        store = JobStore(fake_redis)
        await store.record_completion("instagram", success=True)
        await store.record_completion("tiktok", success=False)

        stats = await store.get_stats()
        assert stats["total"] == 2
        assert stats["success"] == 1
        assert stats["failure"] == 1

    async def test_stats_default_to_zero(self, fake_redis):
        store = JobStore(fake_redis)
        stats = await store.get_stats()
        assert stats == {"total": 0, "success": 0, "failure": 0}
