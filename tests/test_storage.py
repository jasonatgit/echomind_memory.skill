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
        sqlite_store.save_task("user_1", "task_1", "Test", "completed", [], {"lang": "py"})
        tasks = sqlite_store.load_tasks()
        match = [t for t in tasks if t["id"] == "user_1:task_1"]
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
