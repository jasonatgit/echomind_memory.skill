"""Tests for SQLite storage layer — CRUD, transactions, migrations."""

import json


class TestSqliteStoreInit:
    """Verify store initialisation and schema."""

    def test_connect_and_create_tables(self, sqlite_store):
        """Connection + table creation succeed."""
        assert sqlite_store._conn is not None
        tables = sqlite_store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = [r[0] for r in tables]
        expected = [
            "context_archive", "context_memory", "experience_memory",
            "knowledge_memory", "reflections", "research_notes",
            "research_papers", "session_transcripts", "task_memory",
            "user_memory",
        ]
        for t in expected:
            assert t in names, f"Missing table: {t}"

    def test_schema_version(self, sqlite_store):
        """PRAGMA user_version after table creation."""
        cursor = sqlite_store._conn.execute("PRAGMA user_version")
        version = cursor.fetchone()[0]
        assert version >= 3, f"Expected schema v3+, got v{version}"


class TestCrud:
    """Basic CRUD operations for each memory type."""

    def test_save_and_load_user(self, sqlite_store):
        sqlite_store.save_user("user_1", {"style": "concise"}, {"time": "morning"}, [])
        users = sqlite_store.load_users()
        match = [u for u in users if u["user_id"] == "user_1"]
        assert len(match) == 1
        # preferences stored under platform-aware _default wrapper
        assert match[0]["preferences"] == {"_default": {"style": "concise"}}
        assert match[0]["habits"] == {"time": "morning"}

    def test_save_and_load_task(self, sqlite_store):
        from core.storage.sqlite_store import stable_memory_key
        sqlite_store.save_task("user_1", "task_1", "Test", "completed", [], {"lang": "py"})
        tasks = sqlite_store.load_tasks()
        match = [t for t in tasks if t["id"] == stable_memory_key("user_1", "task_1")]
        assert len(match) == 1
        assert match[0]["title"] == "Test"

    def test_save_and_load_experience(self, sqlite_store):
        sqlite_store.save_experience("user_1", "development", 1, [], "Success", "py")
        exps = sqlite_store.load_experiences()
        assert len(exps) >= 1

    def test_save_and_load_knowledge(self, sqlite_store):
        sqlite_store.save_knowledge(
            "know_1", "python", "sorted() is O(n log n)", {"category": "builtins"},
        )
        knowledge = sqlite_store.load_knowledge()
        match = [k for k in knowledge if k["id"] == "know_1"]
        assert len(match) == 1

    def test_save_and_load_context(self, sqlite_store):
        sqlite_store.save_context("session_1", "user_1", [{"role": "user", "content": "hi"}])
        contexts = sqlite_store.load_contexts()
        match = [c for c in contexts if c["session_id"] == "session_1"]
        assert len(match) == 1


class TestMigrations:
    """Schema migration system tests."""

    def test_migration_v4_last_access_at(self, sqlite_store):
        tables = ["user_memory", "task_memory", "experience_memory",
                   "context_memory", "knowledge_memory", "research_papers"]
        for table in tables:
            cursor = sqlite_store._conn.execute(f"PRAGMA table_info({table})")
            cols = [r[1] for r in cursor.fetchall()]
            assert "last_access_at" in cols, f"{table} missing last_access_at"

    def test_migration_v5_context_archive(self, sqlite_store):
        tables = sqlite_store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        names = [r[0] for r in tables]
        assert "context_archive" in names

    def test_migration_v6_language_indexes(self, sqlite_store):
        indexes = sqlite_store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
        names = [r[0] for r in indexes]
        assert "idx_task_language" in names
        assert "idx_experience_language" in names
        assert "idx_knowledge_language" in names

    def test_migration_idempotent(self, sqlite_store):
        sqlite_store._run_schema_migrations()
        sqlite_store._run_schema_migrations()
        assert True


class TestTransaction:
    """Transaction context manager."""

    def test_transaction_commit(self, sqlite_store):
        with sqlite_store.transaction():
            sqlite_store.save_user("tx_user", {"key": "val"}, {}, [])
        users = sqlite_store.load_users()
        assert any(u["user_id"] == "tx_user" for u in users)

    def test_transaction_rollback(self, sqlite_store):
        class _TestError(Exception):
            pass
        try:
            with sqlite_store.transaction():
                sqlite_store.save_user("rollback_user", {}, {}, [])
                raise _TestError("rollback")
        except _TestError:
            pass
        users = sqlite_store.load_users()
        assert not any(u["user_id"] == "rollback_user" for u in users)

    def test_normalize_row_none_handling(self, sqlite_store):
        from core.storage.sqlite_store import _normalize_row
        row = {"user_id": "test", "preferences": None, "habits": None}
        normalized = _normalize_row(row)
        assert normalized["preferences"] == "{}"
        assert normalized["habits"] == "{}"


class TestReflectionPersistence:
    """P1-A persistence contract (Bug 1 / Bug 4 regression)."""

    def test_save_reflection_nested_schema_roundtrip(self, sqlite_store):
        sqlite_store.save_reflection({
            "id": "reflection:user_1:1",
            "user_id": "user_1",
            "platform": "test",
            "source_episodic_ids": ["ep_1"],
            "reflection": {
                "key_insights": ["insight a"],
                "user_preferences": ["lang=en"],
                "procedural_rules": ["rule 1"],
                "new_knowledge": ["knowledge a"],
                "importance_scores": {"relevance": 0.5},
                "forget_suggestions": ["old fact"],
                "confidence": 0.8,
            },
            "meta": {"source": "reflection"},
        })
        rows = sqlite_store._conn.execute(
            "SELECT key_insights, new_knowledge, confidence FROM reflections"
            " WHERE id='reflection:user_1:1'"
        ).fetchall()
        assert len(rows) == 1
        key_insights = json.loads(rows[0]["key_insights"])
        new_knowledge = json.loads(rows[0]["new_knowledge"])
        assert key_insights == ["insight a"]
        assert new_knowledge == ["knowledge a"]
        assert rows[0]["confidence"] == 0.8

    def test_save_reflection_unique_ids_do_not_overwrite(self, sqlite_store):
        sqlite_store.save_reflection({
            "id": "reflection:user_1:1",
            "user_id": "user_1",
            "platform": "test",
            "reflection": {"key_insights": ["first"], "confidence": 0.7},
        })
        sqlite_store.save_reflection({
            "id": "reflection:user_1:2",
            "user_id": "user_1",
            "platform": "test",
            "reflection": {"key_insights": ["second"], "confidence": 0.9},
        })
        cnt = sqlite_store._conn.execute(
            "SELECT COUNT(*) AS c FROM reflections WHERE user_id='user_1'"
        ).fetchone()["c"]
        assert cnt == 2


class TestDailyReflectionCount:
    """P5-B per-(user, date) counter persistence."""

    def test_reflection_daily_count_table_exists(self, sqlite_store):
        tables = sqlite_store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        names = [r[0] for r in tables]
        assert "reflection_daily_count" in names

    def test_increment_daily_reflection_count(self, sqlite_store):
        assert sqlite_store.get_daily_reflection_count("u", "2026-08-15") == 0
        first = sqlite_store.increment_daily_reflection_count("u", "2026-08-15")
        second = sqlite_store.increment_daily_reflection_count("u", "2026-08-15")
        assert first == 1
        assert second == 2
        # Different user / different date are isolated
        assert sqlite_store.get_daily_reflection_count("v", "2026-08-15") == 0
        assert sqlite_store.get_daily_reflection_count("u", "2026-08-16") == 0


class TestDeleteExpiredNoMissingColumn:
    """B2: delete_expired must not raise for tables lacking last_access_at."""

    def test_ttl_on_note_reflection_transcript_does_not_raise(self, sqlite_store):
        sqlite_store.save_reflection({
            "id": "r:1", "user_id": "u", "platform": "t",
            "reflection": {"key_insights": ["x"], "confidence": 0.8},
        })
        # note / reflection / transcript have no last_access_at column; a TTL
        # over them used to raise OperationalError (no such column) → 500.
        counts = sqlite_store.delete_expired({
            "note": 1, "reflection": 1, "transcript": 1,
            "knowledge": 0,  # <= 0 is skipped
        })
        # The reflection we just stored is younger than 1 day, so 0 deleted —
        # but critically no exception was raised.
        assert counts.get("reflection", -1) >= 0


class TestStableTaskKey:
    """B5/B6: stable, delimiter-safe task primary key."""

    def test_stable_memory_key_is_deterministic_and_unambiguous(self):
        from core.storage.sqlite_store import stable_memory_key
        a = stable_memory_key("u", "sess:turn3")
        b = stable_memory_key("u", "sess:turn3")
        c = stable_memory_key("u:sess", "turn3")
        assert a == b
        assert a != c  # no ambiguity collapse from the old ":" join

    def test_delete_task_by_pair(self, sqlite_store):
        from core.storage.sqlite_store import stable_memory_key
        sqlite_store.save_task("u1", "s:1", "T", "completed", [], {})
        assert sqlite_store.delete_task("u1", "s:1") is True
        tasks = sqlite_store.load_tasks()
        assert not any(t["id"] == stable_memory_key("u1", "s:1") for t in tasks)
        # Deleting a non-existent pair returns False.
        assert sqlite_store.delete_task("u1", "missing") is False
