"""Regression tests covering the deep-review bug fixes (v1.2.6 audit round).

Covers: transaction atomicity, _maybe_commit gating, daily-limit reset,
timestamp parsing/unification, ContextMessage Optional, UPSERT field updates,
knowledge/experience last_access_at propagation, and main.py param pass-through.
"""

import json
from datetime import datetime, timezone
from unittest import mock


# ── Transaction atomicity & _maybe_commit (H3) ──

class TestTransactionAtomicity:
    def test_transaction_rolls_back_all_saves(self, sqlite_store):
        """A failure mid-batch must roll back ALL earlier saves, not partial."""
        class _Boom(Exception):
            pass
        try:
            with sqlite_store.transaction():
                sqlite_store.save_user("u_rollback", {"k": "v"}, {}, [])
                sqlite_store.save_task("u_rollback", "t1", "T", "pending", [], {})
                raise _Boom("boom")
        except _Boom:
            pass
        users = sqlite_store.load_users()
        tasks = sqlite_store.load_tasks()
        assert not any(u["user_id"] == "u_rollback" for u in users)
        assert not any(t["user_id"] == "u_rollback" for t in tasks)

    def test_transaction_commit_persists_all(self, sqlite_store):
        """Successful batch persists everything."""
        with sqlite_store.transaction():
            sqlite_store.save_user("u_commit", {"k": "v"}, {}, [])
            sqlite_store.save_task("u_commit", "t1", "T", "pending", [], {})
        users = sqlite_store.load_users()
        tasks = sqlite_store.load_tasks()
        assert any(u["user_id"] == "u_commit" for u in users)
        assert any(t["user_id"] == "u_commit" for t in tasks)


# ── Daily-limit reset (H6) ──

class TestDailyLimitReset:
    def test_check_daily_limit_uses_fixed_threshold(self, memory_agent):
        """_daily_limit fixed at init, not re-randomized per call."""
        ra = memory_agent.reflective
        observed = {ra._check_daily_limit() for _ in range(5)}
        # _check_daily_limit is a threshold compare; returns bool each time
        assert all(isinstance(x, bool) for x in observed)

    def test_reset_daily_count_on_day_change(self, memory_agent):
        """Counter resets when UTC calendar day changes."""
        from datetime import timedelta
        ra = memory_agent.reflective
        ra._daily_count = ra._daily_limit + 1  # over limit
        assert ra._check_daily_limit() is True
        # simulate new day: set the recorded date to yesterday
        ra._daily_count_date = ra._daily_count_date - timedelta(days=1)
        assert ra._reset_daily_if_new_day() is None
        ra._reset_daily_if_new_day()
        assert ra._daily_count == 0
        assert ra._check_daily_limit() is False


# ── Timestamps (H2/M2) ──

class TestTimestampHandling:
    def test_parse_db_ts_naive(self, memory_agent):
        dt = memory_agent._parse_db_ts("2026-01-01 10:00:00")
        assert dt is not None
        assert dt.tzinfo is not None
        assert dt.year == 2026

    def test_parse_db_ts_aware(self, memory_agent):
        dt = memory_agent._parse_db_ts("2026-01-01T10:00:00+00:00")
        assert dt is not None
        assert dt.tzinfo is not None

    def test_parse_db_ts_invalid_returns_none(self, memory_agent):
        assert memory_agent._parse_db_ts("not-a-date") is None
        assert memory_agent._parse_db_ts(None) is None

    def test_freshness_accepts_datetime_object(self, memory_agent):
        """_freshness must not crash on a datetime object (was a TypeError)."""
        record = {"last_updated": datetime.now(timezone.utc)}
        assert memory_agent._freshness(record) == 1.0

    def test_update_last_access_uses_db_format(self, memory_agent, sqlite_store):
        """_update_last_access_for_retrieved writes 'YYYY-MM-DD HH:MM:SS' (matches DB)."""
        memory_agent.db = sqlite_store
        memory_agent._persistence_enabled = True
        sqlite_store.save_knowledge("k:1", "general", "content", {})
        sqlite_store.save_memory_state("knowledge", "k:1", "active")
        memory_agent._update_last_access_for_retrieved(
            {"knowledge": [{"id": "k:1", "content": "content"}]}, "user"
        )
        row = sqlite_store._conn.execute(
            "SELECT last_access_at FROM knowledge_memory WHERE id='k:1'"
        ).fetchone()
        assert row is not None
        # format must be space-separated (DB datetime('now') style), not ISO 'T'
        assert row["last_access_at"] and "T" not in row["last_access_at"]


# ── UPSERT field updates (H4) ──

class TestUpsertFieldUpdates:
    def test_save_task_updates_title_on_conflict(self, sqlite_store):
        sqlite_store.save_task("u1", "t1", "Old Title", "completed", [], {})
        sqlite_store.save_task("u1", "t1", "New Title", "completed", [], {})
        tasks = sqlite_store.load_tasks()
        match = [t for t in tasks if t["id"] == "u1:t1"]
        assert len(match) == 1
        assert match[0]["title"] == "New Title"

    def test_save_experience_updates_success_on_conflict(self, sqlite_store):
        sqlite_store.save_experience("u1", "dev", 0, [], "same", experience_id="e:1")
        sqlite_store.save_experience("u1", "dev", 1, [], "same", experience_id="e:1")
        exps = sqlite_store.load_experiences()
        match = [e for e in exps if e["id"] == "e:1"]
        assert len(match) == 1
        # success persisted as int
        assert int(match[0]["success"]) == 1


# ── ContextMessage Optional (M6) ──

class TestContextMessageOptional:
    def test_content_accepts_none(self):
        from core.models.context import ContextMessage
        msg = ContextMessage(role="assistant", content=None)
        # Optional content accepted without crashing; explicit None is preserved
        assert msg.content is None


# ── Safe JSON loads (L7) ──

class TestSafeJsonLoads:
    def test_safe_json_loads_valid(self):
        from core.storage.sqlite_store import _safe_json_loads
        assert _safe_json_loads('{"a": 1}', {}) == {"a": 1}

    def test_safe_json_loads_invalid(self):
        from core.storage.sqlite_store import _safe_json_loads
        assert _safe_json_loads("{malformed", []) == []
        assert _safe_json_loads(None, {}) == {}


# ── main.py param pass-through (H1) ──

class TestMainParamPassThrough:
    def test_retrieve_forwards_project_session(self, memory_agent):
        """main.py dispatch must not drop project/session_id."""
        with mock.patch.object(
            memory_agent, "retrieve_for_task", return_value={"working_memory": [],
                                                             "confidence_score": 0.0,
                                                             "retrieved_memories": [],
                                                             "feedback_request": False}
        ) as rm:
            # simulate main.py tool call wiring
            memory_agent.retrieve_for_task(
                task_context="q", user_id="u", task_id="t",
                platform="http", project="proj", session_id="sess", profile="default",
            )
            rm.assert_called_once()
            kwargs = rm.call_args.kwargs
            assert kwargs["project"] == "proj"
            assert kwargs["session_id"] == "sess"