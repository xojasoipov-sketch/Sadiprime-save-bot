from __future__ import annotations

from bot.services.search_sessions import create_session, get_candidate
from downloader.music_search import SearchCandidate


def make_candidates():
    return [
        SearchCandidate(url="https://www.youtube.com/watch?v=a", title="A", duration_seconds=100),
        SearchCandidate(url="https://www.youtube.com/watch?v=b", title="B", duration_seconds=200),
    ]


class TestSearchSessions:
    async def test_create_and_get_candidate_round_trips(self, fake_redis):
        candidates = make_candidates()
        session_id = await create_session(fake_redis, user_id=1, candidates=candidates)

        result = await get_candidate(fake_redis, session_id=session_id, index=0, requester_id=1)

        assert result == candidates[0]

    async def test_get_candidate_by_second_index(self, fake_redis):
        candidates = make_candidates()
        session_id = await create_session(fake_redis, user_id=1, candidates=candidates)

        result = await get_candidate(fake_redis, session_id=session_id, index=1, requester_id=1)

        assert result == candidates[1]

    async def test_wrong_requester_is_rejected(self, fake_redis):
        candidates = make_candidates()
        session_id = await create_session(fake_redis, user_id=1, candidates=candidates)

        result = await get_candidate(fake_redis, session_id=session_id, index=0, requester_id=999)

        assert result is None

    async def test_out_of_range_index_returns_none(self, fake_redis):
        candidates = make_candidates()
        session_id = await create_session(fake_redis, user_id=1, candidates=candidates)

        result = await get_candidate(fake_redis, session_id=session_id, index=99, requester_id=1)

        assert result is None

    async def test_unknown_session_returns_none(self, fake_redis):
        result = await get_candidate(
            fake_redis, session_id="does-not-exist", index=0, requester_id=1
        )
        assert result is None

    async def test_sessions_have_a_ttl(self, fake_redis):
        session_id = await create_session(fake_redis, user_id=1, candidates=make_candidates())
        ttl = await fake_redis.ttl(f"md:searchsession:{session_id}")
        assert 0 < ttl <= 300
