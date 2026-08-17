# EchoMind Memory — SQLite Storage Layer (9 memory types)
# Fix: WAL Enable + write lock + threading import + datetime import

import functools
import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def stable_memory_key(user_id: str, task_id: str) -> str:
    """Deterministic, delimiter-safe composite key for task-scoped records.

    B5/B6 fix: task_id itself can contain ':' (e.g. Hermes "{session}:turn{n}"),
    so the old f"{user_id}:{task_id}" made the primary key ambiguous and
    impossible to split reliably — breaking delete/state lookups. This hashes
    the pair with a NUL separator so the key is unambiguous and stable across
    every call site (task_memory.id, context_memory.session_id,
    knowledge_memory.id, memory_states.memory_id).
    """
    digest = hashlib.sha256(f"{user_id}\x00{task_id}".encode("utf-8")).hexdigest()
    return f"t:{digest[:24]}"


DB_DIR = Path.home() / ".echomind"
DB_PATH = DB_DIR / "memory.db"

# load_* methods use this default LIMIT to prevent unbounded memory growth
# on databases with very large record counts. B8 fix: align with the agents'
# MAX_ITEMS (5000) so a truncation here does not silently drop records the
# in-memory store is expected to hold; memory for 5000 rows is bounded and
# acceptable, and the previous 1000 caused silent, unrecoverable drift.
_LOAD_LIMIT = 5000

# Text columns that should never be None when loaded from DB
# (ALTER TABLE ADD COLUMN leaves NULL in existing rows even with DEFAULT)
_NULLABLE_TEXT_COLS = {
    "session_id", "session_title", "project", "profile", "platform",
    "language", "compressed_summary",
    # JSON columns: ALTER TABLE ADD COLUMN leaves NULL
    "preferences", "habits", "history",
    "steps", "metadata", "tags",
    "steps_sequence",
    "messages",
    "prerequisites", "output_template",
    "authors", "keywords", "key_points",
    "linked_papers",
    "key_decisions",
}

# Default values for JSON columns when NULL is encountered
_JSON_DEFAULTS = {
    "preferences": "{}", "habits": "{}", "history": "[]",
    "steps": "[]", "metadata": "{}", "tags": "[]",
    "steps_sequence": "[]",
    "messages": "[]",
    "prerequisites": "[]", "output_template": "",
    "authors": "[]", "keywords": "[]", "key_points": "[]",
    "linked_papers": "[]",
    "key_decisions": "[]",
}


def _normalize_row(row) -> Dict:
    """Normalize None values in text columns to empty string/json default.
    Returns a mutable dict (converts sqlite3.Row if needed)."""
    if not isinstance(row, dict):
        row = dict(row)
    for k in list(row.keys()):
        if k in _NULLABLE_TEXT_COLS and row[k] is None:
            row[k] = _JSON_DEFAULTS.get(k, "")
    return row


def _safe_json_loads(value, default):
    """Parse a JSON column safely; return default on malformed input."""
    if value is None:
        return default
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default

SCHEMA_VERSION = 3  # v1: 无 profile 列 (v1.1.5-), v2: 有 profile 列 (v1.1.6+), v3: user_memory 复合PK (v1.2.0)

# Incremental migrations beyond v3 (stored as PRAGMA user_version)
# Each entry: (version_num, description, sql_statements_or_callable)
# Version 4+: added incrementally via _run_schema_migrations()
_MIGRATIONS = [
    (4, "Add last_access_at to 6 memory tables",
     [
         "ALTER TABLE user_memory ADD COLUMN last_access_at TEXT DEFAULT ''",
         "ALTER TABLE task_memory ADD COLUMN last_access_at TEXT DEFAULT ''",
         "ALTER TABLE experience_memory ADD COLUMN last_access_at TEXT DEFAULT ''",
         "ALTER TABLE context_memory ADD COLUMN last_access_at TEXT DEFAULT ''",
         "ALTER TABLE knowledge_memory ADD COLUMN last_access_at TEXT DEFAULT ''",
         "ALTER TABLE research_papers ADD COLUMN last_access_at TEXT DEFAULT ''",
         "CREATE INDEX IF NOT EXISTS idx_user_last_access ON user_memory(last_access_at)",
         "CREATE INDEX IF NOT EXISTS idx_task_last_access ON task_memory(last_access_at)",
         "CREATE INDEX IF NOT EXISTS idx_experience_last_access ON experience_memory(last_access_at)",
         "CREATE INDEX IF NOT EXISTS idx_knowledge_last_access ON knowledge_memory(last_access_at)",
         "CREATE INDEX IF NOT EXISTS idx_context_last_access ON context_memory(last_access_at)",
         "CREATE INDEX IF NOT EXISTS idx_papers_last_access ON research_papers(last_access_at)",
     ]),
    (5, "Add context_archive table for evicted session messages",
     [
         "CREATE TABLE IF NOT EXISTS context_archive ("
         " id INTEGER PRIMARY KEY AUTOINCREMENT,"
         " session_id TEXT NOT NULL,"
         " role TEXT NOT NULL,"
         " content TEXT NOT NULL,"
         " archived_at TEXT DEFAULT (datetime('now'))"
         ")",
         "CREATE INDEX IF NOT EXISTS idx_archive_session ON context_archive(session_id)",
     ]),
    (6, "Add language column indexes for faster filtered retrieval",
     [
         "CREATE INDEX IF NOT EXISTS idx_task_language ON task_memory(language)",
         "CREATE INDEX IF NOT EXISTS idx_experience_language ON experience_memory(language)",
         "CREATE INDEX IF NOT EXISTS idx_knowledge_language ON knowledge_memory(language)",
     ]),
    (7, "Add memory_states table for lifecycle tracking",
     [
         "CREATE TABLE IF NOT EXISTS memory_states ("
         " id INTEGER PRIMARY KEY AUTOINCREMENT,"
         " memory_type TEXT NOT NULL,"
         " memory_id TEXT NOT NULL,"
         " state TEXT NOT NULL DEFAULT 'active',"
         " state_changed_at TEXT DEFAULT (datetime('now')),"
         " reason TEXT DEFAULT '',"
         " previous_state TEXT DEFAULT '',"
         " source TEXT DEFAULT 'system',"
         " UNIQUE(memory_type, memory_id)"
         ")",
         "CREATE INDEX IF NOT EXISTS idx_memory_states_lookup ON memory_states(memory_type, memory_id)",
         "CREATE INDEX IF NOT EXISTS idx_memory_states_current ON memory_states(memory_type, state)",
         # Backfill: all existing memories start as 'active'
         "INSERT OR IGNORE INTO memory_states (memory_type, memory_id, state, reason, source) "
         "SELECT 'user', user_id, 'active', 'backfill', 'system' FROM user_memory",
         "INSERT OR IGNORE INTO memory_states (memory_type, memory_id, state, reason, source) "
         "SELECT 'task', id, 'active', 'backfill', 'system' FROM task_memory",
         "INSERT OR IGNORE INTO memory_states (memory_type, memory_id, state, reason, source) "
         "SELECT 'experience', id, 'active', 'backfill', 'system' FROM experience_memory",
         "INSERT OR IGNORE INTO memory_states (memory_type, memory_id, state, reason, source) "
         "SELECT 'context', session_id, 'active', 'backfill', 'system' FROM context_memory",
         "INSERT OR IGNORE INTO memory_states (memory_type, memory_id, state, reason, source) "
         "SELECT 'knowledge', id, 'active', 'backfill', 'system' FROM knowledge_memory",
         "INSERT OR IGNORE INTO memory_states (memory_type, memory_id, state, reason, source) "
         "SELECT 'paper', id, 'active', 'backfill', 'system' FROM research_papers",
     ]),
    (8, "Add knowledge_evolution table for tracking knowledge relationships",
     [
         "CREATE TABLE IF NOT EXISTS knowledge_evolution ("
         " id INTEGER PRIMARY KEY AUTOINCREMENT,"
         " source_id TEXT NOT NULL,"
         " target_id TEXT NOT NULL,"
         " relation_type TEXT NOT NULL,"
         " confidence REAL DEFAULT 0.5,"
         " reason TEXT DEFAULT '',"
         " detection_method TEXT DEFAULT 'jaccard',"
         " created_at TEXT DEFAULT (datetime('now'))"
         ")",
"CREATE INDEX IF NOT EXISTS idx_evolution_source ON knowledge_evolution(source_id)",
          "CREATE INDEX IF NOT EXISTS idx_evolution_target ON knowledge_evolution(target_id)",
      ]),
    (9, "Add provenance columns to knowledge_evolution for memory provenance tracking",
     [
         "ALTER TABLE knowledge_evolution ADD COLUMN origin_agent TEXT DEFAULT ''",
         "ALTER TABLE knowledge_evolution ADD COLUMN origin_session_id TEXT DEFAULT ''",
         "ALTER TABLE knowledge_evolution ADD COLUMN origin_turn INTEGER DEFAULT 0",
     ]),
]
# Tables that need a profile column
_PROFILE_TABLES = [
    "user_memory", "task_memory", "experience_memory",
    "context_memory", "knowledge_memory", "research_papers",
    "research_notes", "session_transcripts",
]


# ── SQLite BUSY retry decorator (Fix 3: concurrent write protection) ──────────

MAX_RETRIES = 3
RETRY_DELAY_MS = 100  # initial delay 100ms, exponential backoff


def _require_conn(method):
    """Decorator: raise RuntimeError if DB not connected (instead of silent return)."""
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        if not self._conn:
            raise RuntimeError(
                f"{method.__name__}: SQLite not connected. Call connect() first."
            )
        return method(self, *args, **kwargs)
    return wrapper


def with_retry_on_busy(max_retries=MAX_RETRIES):
    """Decorator to auto-retry on SQLITE_BUSY.

    WAL + busy_timeout resolves most concurrency conflicts,
    this decorator handles edge-case write failures.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            last_exc = None
            delay = RETRY_DELAY_MS / 1000.0
            for attempt in range(max_retries):
                try:
                    return func(self, *args, **kwargs)
                except sqlite3.OperationalError as e:
                    if "database is locked" not in str(e):
                        raise
                    last_exc = e
                    if attempt < max_retries - 1:
                        time.sleep(delay)
                        delay *= 2  # exponential backoff
            raise RuntimeError(
                f"Write failed after {max_retries} retries: {last_exc}"
            ) from last_exc
        return wrapper
    return decorator


class SqliteStore:
    """SQLite Persistent storage — manage 9 memory data tables"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(DB_PATH)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._lock: Optional[threading.RLock] = None
        self._batch_active = False

    def connect(self):
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # Force checkpoint stale WAL from previous unclean shutdown
        try:
            self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.OperationalError:
            pass
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=10000")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._lock = threading.RLock()
        logger.info(f"Connected to SQLite: {self.db_path} (WAL + busy_timeout=10000)")

    def ensure_tables(self):
        """Create complete 9 memory data tables"""
        if not self._conn:
            return
        with self._lock:
            self._conn.executescript("""
-- 1. User memory: preferences, habits, interaction history
                    CREATE TABLE IF NOT EXISTS user_memory (
                        user_id TEXT NOT NULL,
                        profile TEXT NOT NULL DEFAULT 'default',
                        preferences TEXT DEFAULT '{}',
                        habits TEXT DEFAULT '{}',
                        history TEXT DEFAULT '[]',
                        last_updated TEXT DEFAULT (datetime('now')),
                        last_access_at TEXT DEFAULT '',
                        created_at TEXT DEFAULT (datetime('now')),
                        version INTEGER DEFAULT 1,
                        PRIMARY KEY (user_id, profile)
                    );

                -- 2. Task memory: status, steps, metadata
                CREATE TABLE IF NOT EXISTS task_memory (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    title TEXT,
                    status TEXT,
                    steps TEXT DEFAULT '[]',
                    metadata TEXT DEFAULT '{}',
                    project TEXT DEFAULT 'default',
                    profile TEXT DEFAULT 'default',
                    session_id TEXT DEFAULT '',
                    session_title TEXT DEFAULT '',
                    tags TEXT DEFAULT '[]',
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    language TEXT DEFAULT '',
                    last_access_at TEXT DEFAULT ''
                );

                -- 3. Experience memory: success/failure experience, step sequences
                CREATE TABLE IF NOT EXISTS experience_memory (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    task_type TEXT,
                    success INTEGER,
                    steps_sequence TEXT DEFAULT '[]',
                    summary TEXT,
                    project TEXT DEFAULT 'default',
                    profile TEXT DEFAULT 'default',
                    session_id TEXT DEFAULT '',
                    session_title TEXT DEFAULT '',
                    tags TEXT DEFAULT '[]',
                    created_at TEXT DEFAULT (datetime('now')),
                    frequency INTEGER DEFAULT 1,
                    language TEXT DEFAULT '',
                    last_access_at TEXT DEFAULT ''
                );

                -- 4. Context memory: conversation context, token count, session ID、Platform source
                CREATE TABLE IF NOT EXISTS context_memory (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT,
                    messages TEXT DEFAULT '[]',
                    token_count INTEGER DEFAULT 0,
                    platform TEXT DEFAULT 'default',
                    project TEXT DEFAULT 'default',
                    profile TEXT DEFAULT 'default',
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    last_access_at TEXT DEFAULT ''
                );

                -- 5. Knowledge memory: domain knowledge, structured entries
                CREATE TABLE IF NOT EXISTS knowledge_memory (
                    id TEXT PRIMARY KEY,
                    domain TEXT DEFAULT 'general',
                    content TEXT,
                    metadata TEXT DEFAULT '{}',
                    trust_score REAL DEFAULT 0.5,
                    entry_type TEXT DEFAULT 'fact',
                    prerequisites TEXT DEFAULT '[]',
                    output_template TEXT DEFAULT '',
                    last_verified_at TEXT DEFAULT (datetime('now')),
                    half_life_days INTEGER DEFAULT 90,
                    access_count INTEGER DEFAULT 0,
                    project TEXT DEFAULT 'default',
                    profile TEXT DEFAULT 'default',
                    session_id TEXT DEFAULT '',
                    session_title TEXT DEFAULT '',
                    tags TEXT DEFAULT '[]',
                    user_id TEXT DEFAULT 'default',
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    language TEXT DEFAULT '',
                    last_access_at TEXT DEFAULT ''
                );

                -- 6. Research papers: academic paper metadata
                CREATE TABLE IF NOT EXISTS research_papers (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    authors TEXT DEFAULT '[]',
                    year INTEGER,
                    journal TEXT,
                    abstract TEXT DEFAULT '',
                    keywords TEXT DEFAULT '[]',
                    domain TEXT DEFAULT 'general',
                    paper_type TEXT DEFAULT 'theory',
                    key_points TEXT DEFAULT '[]',
                    importance_score REAL DEFAULT 0.5,
                    metadata TEXT DEFAULT '{}',
                    project TEXT DEFAULT 'default',
                    profile TEXT DEFAULT 'default',
                    user_id TEXT DEFAULT 'default',
                    created_at TEXT DEFAULT (datetime('now')),
                    last_access_at TEXT DEFAULT ''
                );

                -- 7. Research notes: paper reading notes, research leads
                CREATE TABLE IF NOT EXISTS research_notes (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    topic TEXT NOT NULL,
                    content TEXT DEFAULT '',
                    linked_papers TEXT DEFAULT '[]',
                    tags TEXT DEFAULT '[]',
                    project TEXT DEFAULT 'default',
                    profile TEXT DEFAULT 'default',
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                );

                -- 8. Reflection records table（v1.1.0）
                CREATE TABLE IF NOT EXISTS reflections (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    platform TEXT DEFAULT 'default',
                    source_episodic_ids TEXT,
                    key_insights TEXT,
                    user_preferences TEXT,
                    procedural_rules TEXT,
                    new_knowledge TEXT,
                    importance_scores TEXT,
                    forget_suggestions TEXT,
                    confidence REAL DEFAULT 0.0,
                    meta TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                -- 9. Session transcripts: full conversation history + Compression summary
                CREATE TABLE IF NOT EXISTS session_transcripts (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT,
                    project TEXT DEFAULT 'default',
                    profile TEXT DEFAULT 'default',
                    messages TEXT,
                    compressed_summary TEXT DEFAULT '',
                    key_decisions TEXT DEFAULT '[]',
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                );

                -- 10. Reflection daily counters: per-(user, date) reflection quota
                -- consumed by the daily limit. Persisted so the limit survives
                -- process restarts and is isolated per user (P5-B).
                CREATE TABLE IF NOT EXISTS reflection_daily_count (
                    user_id TEXT NOT NULL,
                    date TEXT NOT NULL,
                    count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, date)
                );

                -- index
                CREATE INDEX IF NOT EXISTS idx_task_project ON task_memory(project);
                CREATE INDEX IF NOT EXISTS idx_task_updated ON task_memory(updated_at);
                CREATE INDEX IF NOT EXISTS idx_task_session ON task_memory(session_id);
                CREATE INDEX IF NOT EXISTS idx_experience_user ON experience_memory(user_id);
                CREATE INDEX IF NOT EXISTS idx_experience_project ON experience_memory(project);
                CREATE INDEX IF NOT EXISTS idx_experience_session ON experience_memory(session_id);
                CREATE INDEX IF NOT EXISTS idx_context_user ON context_memory(user_id);
                CREATE INDEX IF NOT EXISTS idx_knowledge_domain ON knowledge_memory(domain);
                CREATE INDEX IF NOT EXISTS idx_knowledge_user ON knowledge_memory(user_id);
                CREATE INDEX IF NOT EXISTS idx_knowledge_project ON knowledge_memory(project);
                CREATE INDEX IF NOT EXISTS idx_research_domain ON research_papers(domain);
                CREATE INDEX IF NOT EXISTS idx_research_user ON research_papers(user_id);
                CREATE INDEX IF NOT EXISTS idx_notes_user ON research_notes(user_id);
                CREATE INDEX IF NOT EXISTS idx_session_transcripts_user ON session_transcripts(user_id);
                -- P6-A: missing join/lookup indexes (idempotent)
                CREATE INDEX IF NOT EXISTS idx_knowledge_content ON knowledge_memory(content);
                CREATE INDEX IF NOT EXISTS idx_task_user_created ON task_memory(user_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_experience_user_created ON experience_memory(user_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_reflections_user ON reflections(user_id, created_at);
            """)
            self._maybe_commit()
            self._migrate_existing_tables()
            # build profile index after migration (ensure profile column exists)
            self._conn.executescript("""
                CREATE INDEX IF NOT EXISTS idx_user_profile ON user_memory(profile);
                CREATE INDEX IF NOT EXISTS idx_task_profile ON task_memory(profile);
                CREATE INDEX IF NOT EXISTS idx_experience_profile ON experience_memory(profile);
                CREATE INDEX IF NOT EXISTS idx_context_profile ON context_memory(profile);
                CREATE INDEX IF NOT EXISTS idx_knowledge_profile ON knowledge_memory(profile);
                CREATE INDEX IF NOT EXISTS idx_papers_profile ON research_papers(profile);
                CREATE INDEX IF NOT EXISTS idx_notes_profile ON research_notes(profile);
                CREATE INDEX IF NOT EXISTS idx_transcripts_profile ON session_transcripts(profile);
            """)
            self._maybe_commit()
            # Auto-migrate: add language column to existing databases (idempotent)
            _LANG_TABLES = ["task_memory", "experience_memory", "knowledge_memory"]
            for table in _LANG_TABLES:
                try:
                    self._conn.execute(
                        f"ALTER TABLE {table} ADD COLUMN language TEXT DEFAULT ''"
                    )
                    logger.debug("Migration: added language column to %s", table)
                except sqlite3.OperationalError:
                    pass
            # Auto-migrate: backfill metadata.category from domain column (idempotent)
            try:
                self._conn.execute("""
                    UPDATE knowledge_memory
                    SET metadata = json_set(metadata, '$.category', domain)
                    WHERE json_extract(metadata, '$.category') IS NULL
                """)
                self._maybe_commit()
            except sqlite3.OperationalError:
                pass
            logger.info("All 9 memory tables ensured")
        # Note: _run_schema_migrations() intentionally OUTSIDE the lock to avoid
        # deadlock — it manages its own transaction with BEGIN IMMEDIATE.
        self._run_schema_migrations()

    def _run_schema_migrations(self):
        """Apply incremental schema migrations beyond SCHEMA_VERSION.

        Reads PRAGMA user_version and applies each migration in order.
        All migrations run inside a single transaction — rolled back on failure.
        """
        if not self._conn:
            return
        cursor = self._conn.execute("PRAGMA user_version")
        current = cursor.fetchone()[0]
        if not _MIGRATIONS or current >= _MIGRATIONS[-1][0]:
            return
        try:
            with self._lock:
                self._conn.execute("BEGIN IMMEDIATE TRANSACTION")
                for version, desc, stmts in _MIGRATIONS:
                    if version <= current:
                        continue
                    for stmt in stmts:
                        try:
                            self._conn.execute(stmt)
                        except sqlite3.OperationalError as e:
                            err = str(e).lower()
                            if "duplicate column" in err or "already exists" in err:
                                # B9: an idempotent DDL already applied in a
                                # prior (possibly partial) run. Log rather than
                                # advance silently so a half-applied migration
                                # is observable; the remaining stmts still run,
                                # and user_version is only bumped after the whole
                                # migration's stmts complete.
                                logger.warning(
                                    "Migration v%d skip (already applied): %s",
                                    version, err)
                                continue
                            raise
                    self._conn.execute(f"PRAGMA user_version = {version}")
                    logger.info("Migration v%d: %s", version, desc)
                self._maybe_commit()
        except Exception as e:
            self._conn.rollback()
            logger.error("Schema migration failed, rolled back: %s", e, exc_info=True)
            raise RuntimeError(f"Schema migration failed: {e}") from e

    def transaction(self):
        """Context manager for atomic batch writes.

        Usage: with store.transaction(): store.save_user(...); store.save_task(...)
        Uses BEGIN IMMEDIATE to acquire write lock upfront. While batch-active,
        save_* methods defer auto-commit so the batch is atomic (rollback on error).
        """
        def _set_batch(on):
            self._batch_active = on
        return _TransactionContext(self._conn, self._lock, _set_batch)

    def _maybe_commit(self):
        """Commit unless an outer batch transaction is active.

        Inside `transaction()`, defer the commit so the whole batch is atomic
        (rollback on any failure). When no batch is active, commit immediately.
        """
        if not self._batch_active:
            self._conn.commit()



    def _migrate_existing_tables(self):
        """Backward-compatible: add missing columns, transactional + schema_version flag

        - Atomic: BEGIN IMMEDIATE TRANSACTION + COMMIT / ROLLBACK
        - Idempotent: PRAGMA user_version check + per-table column detection
        - Preserves legacy platform migration logic
        """
        # Detect current schema version
        cursor = self._conn.execute("PRAGMA user_version")
        current_version = cursor.fetchone()[0]
        if current_version >= SCHEMA_VERSION:
            return  # already at latest schema

        try:
            # IMMEDIATE acquires write lock, prevents profile interference
            self._conn.execute("BEGIN IMMEDIATE TRANSACTION")

            # 1. Add profile column (8 tables)
            for table in _PROFILE_TABLES:
                cursor = self._conn.execute(f"PRAGMA table_info({table})")
                columns = [row[1] for row in cursor.fetchall()]
                if "profile" not in columns:
                    self._conn.execute(
                        f"ALTER TABLE {table} ADD COLUMN profile TEXT DEFAULT 'default'"
                    )
                    logger.info(f"Migration: added profile column to {table}")

            # 2. Legacy platform column migration (keep compat)
            ctx_cols = [r[1] for r in self._conn.execute(
                "PRAGMA table_info(context_memory)").fetchall()]
            if "platform" not in ctx_cols:
                self._conn.execute(
                    "ALTER TABLE context_memory ADD COLUMN platform TEXT DEFAULT 'default'"
                )
                logger.info("Migration: added platform column to context_memory")

            # 3. Migrate user_memory to composite PK (v2→v3)
            um_cols = [r[1] for r in self._conn.execute(
                "PRAGMA table_info(user_memory)").fetchall()]
            # Check if old single-PK schema
            pk_info = self._conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='user_memory'"
            ).fetchone()
            if pk_info and "user_id TEXT PRIMARY KEY" in pk_info[0]:
                logger.info("Migration v3: recreating user_memory with composite PK")
                self._conn.execute("""
                    CREATE TABLE user_memory_new (
                        user_id TEXT NOT NULL,
                        profile TEXT NOT NULL DEFAULT 'default',
                        preferences TEXT DEFAULT '{}',
                        habits TEXT DEFAULT '{}',
                        history TEXT DEFAULT '[]',
                        last_updated TEXT DEFAULT (datetime('now')),
                        last_access_at TEXT DEFAULT '',
                        created_at TEXT DEFAULT (datetime('now')),
                        version INTEGER DEFAULT 1,
                        PRIMARY KEY (user_id, profile)
                    )
                """)
                # Copy only columns that exist in the old table
                old_cols = [c for c in um_cols if c not in ('habits', 'history', 'version')
                            or c in um_cols]
                insert_cols = ["user_id", "preferences"]
                select_cols = ["user_id", "COALESCE(preferences, '{}')"]
                if "profile" in um_cols:
                    insert_cols.append("profile")
                    select_cols.append("COALESCE(NULLIF(profile,''), 'default')")
                if "habits" in um_cols:
                    insert_cols.append("habits")
                    select_cols.append("COALESCE(habits, '{}')")
                if "history" in um_cols:
                    insert_cols.append("history")
                    select_cols.append("COALESCE(history, '[]')")
                if "last_updated" in um_cols:
                    insert_cols.append("last_updated")
                    select_cols.append("last_updated")
                if "last_access_at" in um_cols:
                    insert_cols.append("last_access_at")
                    select_cols.append("COALESCE(last_access_at, '')")
                if "created_at" in um_cols:
                    insert_cols.append("created_at")
                    select_cols.append("COALESCE(created_at, datetime('now'))")
                if "version" in um_cols:
                    insert_cols.append("version")
                    select_cols.append("version")
                ins_sql = f"INSERT INTO user_memory_new ({', '.join(insert_cols)}) SELECT {', '.join(select_cols)} FROM user_memory"
                self._conn.execute(ins_sql)
                self._conn.execute("DROP TABLE user_memory")
                self._conn.execute("ALTER TABLE user_memory_new RENAME TO user_memory")
                logger.info("Migration v3: user_memory composite PK complete")

            # 4. Write schema version number
            self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self._maybe_commit()
            logger.info(
                f"Migration: {len(_PROFILE_TABLES)} tables migrated "
                f"to schema v{SCHEMA_VERSION} (profile column)"
            )
        except Exception as e:
            self._conn.rollback()
            logger.error(f"Migration failed, rolled back: {e}")
            raise RuntimeError(
                f"DB migration to schema v{SCHEMA_VERSION} failed: {e}"
            ) from e
    @_require_conn
    def load_all(self) -> Dict[str, Any]:
        raw = {
            "users": self.load_users(),
            "tasks": self.load_tasks(),
            "experiences": self.load_experiences(),
            "contexts": self.load_contexts(),
            "knowledge": self.load_knowledge(),
            "research_papers": self.load_research_papers(),
            "research_notes": self.load_research_notes(),
        }
        for key, rows in raw.items():
            if isinstance(rows, list):
                for row in rows:
                    if isinstance(row, dict):
                        _normalize_row(row)
        return raw

    @_require_conn
    def load_users(self) -> List[Dict]:
        rows = self._conn.execute(
            "SELECT * FROM user_memory ORDER BY last_updated DESC LIMIT ?",
            (_LOAD_LIMIT,)).fetchall()
        if len(rows) >= _LOAD_LIMIT:
            logger.warning("load_users: truncated at LIMIT=%d (more rows in DB)", _LOAD_LIMIT)
        return [{k: (_safe_json_loads(r[k], {} if k == 'preferences' else []) if k in ('preferences','habits','history') else r[k])
                 for k in r.keys()} for r in (_normalize_row(r) or r for r in rows)]

    @_require_conn
    def load_tasks(self) -> List[Dict]:
        rows = self._conn.execute(
            "SELECT * FROM task_memory ORDER BY updated_at DESC LIMIT ?",
            (_LOAD_LIMIT,)).fetchall()
        if len(rows) >= _LOAD_LIMIT:
            logger.warning("load_tasks: truncated at LIMIT=%d (more rows in DB)", _LOAD_LIMIT)
        return [{k: (_safe_json_loads(r[k], {'steps': [], 'metadata': {}, 'tags': []}[k]) if k in ('steps','metadata','tags') else r[k])
                 for k in r.keys()} for r in (_normalize_row(r) or r for r in rows)]

    @_require_conn
    def load_experiences(self) -> List[Dict]:
        rows = self._conn.execute(
            "SELECT * FROM experience_memory ORDER BY created_at DESC LIMIT ?",
            (_LOAD_LIMIT,)).fetchall()
        if len(rows) >= _LOAD_LIMIT:
            logger.warning("load_experiences: truncated at LIMIT=%d (more rows in DB)", _LOAD_LIMIT)
        return [{k: (_safe_json_loads(r[k], [] if k == 'steps_sequence' else []) if k in ('steps_sequence','tags') else r[k])
                 for k in r.keys()} for r in (_normalize_row(r) or r for r in rows)]

    @_require_conn
    def load_contexts(self) -> List[Dict]:
        rows = self._conn.execute(
            "SELECT * FROM context_memory ORDER BY updated_at DESC LIMIT ?",
            (_LOAD_LIMIT,)).fetchall()
        if len(rows) >= _LOAD_LIMIT:
            logger.warning("load_contexts: truncated at LIMIT=%d (more rows in DB)", _LOAD_LIMIT)
        return [{k: (_safe_json_loads(r[k], []) if k == 'messages' else r[k])
                 for k in r.keys()} for r in (_normalize_row(r) or r for r in rows)]

    @_require_conn
    def load_knowledge(self) -> List[Dict]:
        rows = self._conn.execute(
            "SELECT * FROM knowledge_memory ORDER BY updated_at DESC LIMIT ?",
            (_LOAD_LIMIT,)).fetchall()
        if len(rows) >= _LOAD_LIMIT:
            logger.warning("load_knowledge: truncated at LIMIT=%d (more rows in DB)", _LOAD_LIMIT)
        return [{k: (_safe_json_loads(r[k], {'metadata': {}, 'prerequisites': [], 'tags': []}[k]) if k in ('metadata','prerequisites','tags') else r[k])
                 for k in r.keys()} for r in (_normalize_row(r) or r for r in rows)]

    @_require_conn
    def load_research_papers(self, domain: str = None, project: str = None,
                             user_id: str = None, limit: int = 100) -> List[Dict]:
        where = []
        params = []
        if domain:
            where.append("domain=?")
            params.append(domain)
        if project:
            where.append("project=?")
            params.append(project)
        if user_id:
            where.append("user_id=?")
            params.append(user_id)
        w = " WHERE " + " AND ".join(where) if where else ""
        rows = self._conn.execute(
            f"SELECT * FROM research_papers{w} ORDER BY importance_score DESC LIMIT ?",
            params + [limit]).fetchall()
        return [{k: (_safe_json_loads(r[k], [] if k in ('authors','keywords','key_points') else {}) if k in ('authors','keywords','key_points','metadata') else r[k])
                 for k in r.keys()} for r in (_normalize_row(r) or r for r in rows)]

    @_require_conn
    def load_research_notes(self, user_id: str = None, project: str = None) -> List[Dict]:
        where = []
        params = []
        if user_id:
            where.append("user_id=?")
            params.append(user_id)
        if project:
            where.append("project=?")
            params.append(project)
        w = " WHERE " + " AND ".join(where) if where else ""
        rows = self._conn.execute(
            f"SELECT * FROM research_notes{w} ORDER BY updated_at DESC").fetchall()
        return [{k: (_safe_json_loads(r[k], []) if k in ('linked_papers','tags') else r[k])
                 for k in r.keys()} for r in (_normalize_row(r) or r for r in rows)]

    # ═══════════════════════════════════════════════════
    # SAVE
    # ═══════════════════════════════════════════════════


    def _merge_platform_prefs(self, existing_prefs, platform_prefs, platform):
        """Merge platform-specific preferences into existing structure.

        Handles multiple formats:
          - {"response_style": "concise"}  # legacy flat
          - {"_default": {...}, "hermes": {...}}  # multi-platform
          - {"_default": {"_default": {...}, ...}}  # double-nested (bug recovery)

        Preserves top-level metadata keys (e.g. rl_weights) outside _default
        so that load_rl_weights can find them.
        """
        if not isinstance(existing_prefs, dict):
            existing_prefs = {}

        merged = dict(existing_prefs)

        # Extract metadata keys that should stay at top level (not inside _default)
        _TOP_LEVEL_KEYS = {"rl_weights"}
        top_level_extras = {}
        for k in list(merged.keys()):
            if k in _TOP_LEVEL_KEYS:
                top_level_extras[k] = merged.pop(k)

        # Recover from double-nested _default (bug introduced in earlier versions)
        if isinstance(merged.get("_default"), dict) and "_default" in merged["_default"]:
            inner = merged["_default"]
            # Preserve top-level platform keys before promoting inner structure
            for k, v in merged.items():
                if k != "_default":
                    inner[k] = v
            merged = inner

        # Ensure _default key exists
        if "_default" not in merged:
            non_default = {k: v for k, v in merged.items() if k != "_default"}
            merged = {"_default": non_default} if non_default else {"_default": {}}

        merged[platform] = platform_prefs
        if platform != "_default":
            merged["_default"].update(platform_prefs)

        # Restore top-level metadata keys
        merged.update(top_level_extras)
        return merged
    @with_retry_on_busy()
    @_require_conn
    def save_user(self, user_id: str, preferences: Dict = None, habits: Dict = None,
                  history: List = None, version: int = 1, platform: str = None,
                  profile: str = "default"):
        with self._lock:
            if platform:
                existing = self._get_user_raw(user_id, profile)
                preferences = self._merge_platform_prefs(
                    existing.get("preferences", {}), preferences or {}, platform)
            else:
                # No platform: merge into _default, preserving existing platform keys
                existing = self._get_user_raw(user_id, profile)
                existing_prefs = existing.get("preferences", {})
                if isinstance(existing_prefs, dict) and "_default" in existing_prefs:
                    existing_prefs["_default"].update(preferences or {})
                    preferences = existing_prefs
                else:
                    preferences = {"_default": preferences or {}}
            self._conn.execute("""
                INSERT INTO user_memory (user_id, preferences, habits, history, profile, last_updated, last_access_at, version)
                VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'), ?)
                ON CONFLICT(user_id, profile) DO UPDATE SET
                    preferences=json_set(excluded.preferences, '$.rl_weights',
                        COALESCE(json_extract(user_memory.preferences, '$.rl_weights'), json('{}'))),
                    habits=excluded.habits,
                    history=excluded.history, last_updated=datetime('now'),
                    last_access_at=datetime('now'),
                    version=COALESCE(user_memory.version, 0) + 1
            """, (user_id,
                  json.dumps(preferences, ensure_ascii=False),
                  json.dumps(habits or {}, ensure_ascii=False),
                  json.dumps(history or [], ensure_ascii=False),
                  profile,
                  version))
            self._maybe_commit()

    def _get_user_raw(self, user_id: str, profile: str = "default") -> Dict:
        row = self._conn.execute(
            "SELECT * FROM user_memory WHERE user_id = ? AND profile = ?",
            (user_id, profile)
        ).fetchone()
        if not row: return {}
        result = {k: row[k] for k in row.keys()}
        for k in ('preferences', 'habits', 'history'):
            try:
                result[k] = json.loads(result[k])
            except (json.JSONDecodeError, TypeError, KeyError):
                result[k] = {} if k in ('preferences', 'habits') else []
        return result

    @with_retry_on_busy()
    @_require_conn
    def save_task(self, user_id: str, task_id: str, title: str, status: str,
                  steps: List = None, metadata: Dict = None,
                  project: str = "default", session_id: str = "",
                  session_title: str = "", tags: List = None,
                  profile: str = "default", language: str = ""):
        with self._lock:
            task_pk = stable_memory_key(user_id, task_id)
            self._conn.execute("""
                INSERT INTO task_memory (id, user_id, title, status, steps, metadata,
                    project, profile, session_id, session_title, tags, language, updated_at, last_access_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status, steps=excluded.steps,
                    metadata=excluded.metadata, title=excluded.title,
                    project=excluded.project, profile=excluded.profile,
                    session_id=excluded.session_id, session_title=excluded.session_title,
                    tags=excluded.tags, language=excluded.language,
                    updated_at=datetime('now'),
                    last_access_at=datetime('now')
            """, (task_pk, user_id, title, status,
                  json.dumps(steps or []), json.dumps(metadata or {}),
                  project, profile, session_id, session_title,
                  json.dumps(tags or []), language))
            self._maybe_commit()

    @with_retry_on_busy()
    @_require_conn
    def save_experience(self, user_id: str, task_type: str, success: bool,
                        steps: List, summary: str, experience_id: str = None,
                        project: str = "default", session_id: str = "",
                        session_title: str = "", tags: List = None,
                        profile: str = "default", language: str = ""):
        with self._lock:
            eid = experience_id or f"{user_id}:{summary[:20]}:{int(datetime.now(timezone.utc).timestamp())}"
            self._conn.execute("""
                INSERT INTO experience_memory (id, user_id, task_type, success,
                    steps_sequence, summary, project, profile, session_id, session_title, tags, language, last_access_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(id) DO UPDATE SET
                    steps_sequence=excluded.steps_sequence,
                    summary=excluded.summary,
                    task_type=excluded.task_type, success=excluded.success,
                    tags=excluded.tags, session_id=excluded.session_id,
                    session_title=excluded.session_title, project=excluded.project,
                    profile=excluded.profile, language=excluded.language,
                    frequency=experience_memory.frequency + 1,
                    last_access_at=datetime('now')
            """, (eid, user_id, task_type, int(success), json.dumps(steps),
                  summary, project, profile, session_id, session_title,
                  json.dumps(tags or []), language))
            self._maybe_commit()

    @with_retry_on_busy()
    @_require_conn
    def save_context(self, session_id: str, user_id: str, messages: List,
                     token_count: int = 0, platform: str = "default",
                     project: str = "default", profile: str = "default"):
        with self._lock:
            self._conn.execute("""
                INSERT INTO context_memory (session_id, user_id, messages, token_count, platform, project, profile, updated_at, last_access_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                ON CONFLICT(session_id) DO UPDATE SET
                    messages=excluded.messages, token_count=excluded.token_count,
                    platform=excluded.platform,
                    updated_at=datetime('now'),
                    last_access_at=datetime('now')
            """, (session_id, user_id, json.dumps(messages, ensure_ascii=False),
                  token_count, platform, project, profile))
            self._maybe_commit()

    @with_retry_on_busy()
    @_require_conn
    def search_knowledge_by_content(self, content: str):
        with self._lock:
            row = self._conn.execute(
                "SELECT id, content FROM knowledge_memory WHERE content = ? LIMIT 1",
                (content,)
            ).fetchone()
            if row:
                return dict(row)
            return None

    @with_retry_on_busy()
    @_require_conn
    def save_knowledge(self, knowledge_id: str, domain: str, content: str,
                       metadata: Dict = None, trust_score: float = 0.5,
                       entry_type: str = "fact", prerequisites: List = None,
                       output_template: str = "", user_id: str = "default",
                       project: str = "default", session_id: str = "",
                       session_title: str = "", tags: List = None,
                       profile: str = "default", language: str = ""):
        with self._lock:
            _acc = 0
            _m = metadata or {}
            if isinstance(_m, dict):
                _raw_acc = _m.get("access_count", 0)
                if isinstance(_raw_acc, (int, float)):
                    _acc = int(_raw_acc)
            self._conn.execute("""
                INSERT INTO knowledge_memory (id, domain, content, metadata, trust_score,
                    entry_type, prerequisites, output_template, user_id, project, profile,
                    session_id, session_title, tags, language, access_count, updated_at, last_access_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                ON CONFLICT(id) DO UPDATE SET
                    content=excluded.content, metadata=excluded.metadata,
                    trust_score=excluded.trust_score, domain=excluded.domain,
                    tags=excluded.tags, project=excluded.project,
                    session_id=excluded.session_id, session_title=excluded.session_title,
                    language=excluded.language,
                    entry_type=excluded.entry_type,
                    prerequisites=excluded.prerequisites,
                    output_template=excluded.output_template,
                    access_count=knowledge_memory.access_count + 1,
                    updated_at=datetime('now'),
                    last_access_at=datetime('now')
            """, (knowledge_id, domain, content, json.dumps(metadata or {}), trust_score,
                  entry_type, json.dumps(prerequisites or []), output_template,
                  user_id, project, profile, session_id, session_title,
                  json.dumps(tags or []), language, _acc))
            self._maybe_commit()

    @with_retry_on_busy()
    @_require_conn
    def save_research_paper(self, paper_id: str, title: str, authors: List = None,
                            year: int = None, journal: str = None, abstract: str = "",
                            keywords: List = None, domain: str = "general",
                            paper_type: str = "theory", key_points: List = None,
                            importance_score: float = 0.5, metadata: Dict = None,
                            project: str = "default", user_id: str = "default",
                            profile: str = "default"):
        with self._lock:
            self._conn.execute("""
                INSERT INTO research_papers (id, title, authors, year, journal,
                    abstract, keywords, domain, paper_type, key_points,
                    importance_score, metadata, project, profile, user_id, last_access_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title, authors=excluded.authors, year=excluded.year,
                    journal=excluded.journal, abstract=excluded.abstract,
                    keywords=excluded.keywords, domain=excluded.domain,
                    paper_type=excluded.paper_type, key_points=excluded.key_points,
                    importance_score=excluded.importance_score,
                    metadata=excluded.metadata, project=excluded.project,
                    profile=excluded.profile, user_id=excluded.user_id,
                    last_access_at=datetime('now')
            """, (paper_id, title, json.dumps(authors or []), year, journal, abstract,
                  json.dumps(keywords or []), domain, paper_type, json.dumps(key_points or []),
                  importance_score, json.dumps(metadata or {}), project, profile, user_id))
            self._maybe_commit()

    @with_retry_on_busy()
    @_require_conn
    def save_research_note(self, note_id: str, user_id: str, topic: str,
                           content: str, linked_papers: List = None, tags: List = None,
                           project: str = "default", profile: str = "default"):
        with self._lock:
            self._conn.execute("""
                INSERT INTO research_notes (id, user_id, topic, content, linked_papers, tags, project, profile)
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    content=excluded.content,
                    linked_papers=excluded.linked_papers, tags=excluded.tags,
                    topic=excluded.topic, project=excluded.project,
                    profile=excluded.profile, user_id=excluded.user_id,
                    updated_at=datetime('now')
            """, (note_id, user_id, topic, content,
                  json.dumps(linked_papers or []), json.dumps(tags or []),
                  project, profile))
            self._maybe_commit()

    # ═══════════════════════════════════════════════════
    # SEARCH
    # ═══════════════════════════════════════════════════

    @_require_conn
    def search_context(self, user_id: str, query: str = None,
                        platform: str = None, limit: int = 3,
                        profile: str = "default") -> List[Dict]:
        where = "WHERE user_id = ? AND profile = ?"
        params = [user_id, profile]
        if platform:
            where += " AND platform = ?"
            params.append(platform)
        if query:
            # Escape LIKE wildcards to prevent unintended broad matching
            safe_query = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            where += " AND messages LIKE ? ESCAPE '\\'"
            params.append(f"%{safe_query}%")
        rows = self._conn.execute(
            f"SELECT * FROM context_memory {where} ORDER BY updated_at DESC LIMIT ?",
            params + [limit]).fetchall()
        return [{k: (_safe_json_loads(r[k], []) if k == "messages" else r[k])
                 for k in r.keys()} for r in rows]

    @with_retry_on_busy()
    @_require_conn
    def save_rl_weights(self, user_id: str, weights: Dict[str, float],
                        profile: str = "default"):
        with self._lock:
            existing = self._get_user_raw(user_id, profile)
            if existing:
                self._conn.execute("""
                    UPDATE user_memory SET preferences = json_set(
                        CASE WHEN json_type(preferences) IS NULL THEN '{}' ELSE preferences END,
                        '$.rl_weights', json(?)
                    ), last_updated = datetime('now'), last_access_at = datetime('now')
                    WHERE user_id = ? AND profile = ?
                """, (json.dumps(weights), user_id, profile))
            else:
                self._conn.execute("""
                    INSERT INTO user_memory (user_id, preferences, profile, last_updated, last_access_at)
                    VALUES (?, json_object('rl_weights', json(?)), ?, datetime('now'), datetime('now'))
                """, (user_id, json.dumps(weights), profile))
            self._maybe_commit()

    @_require_conn
    def load_rl_weights(self, user_id: str, profile: str = None) -> Optional[Dict[str, float]]:
        if profile:
            row = self._conn.execute(
                "SELECT preferences FROM user_memory WHERE user_id = ? AND profile = ?",
                (user_id, profile),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT preferences FROM user_memory WHERE user_id = ?", (user_id,)
            ).fetchone()
        if row:
            try:
                prefs = json.loads(row["preferences"])
                rlw = prefs.get("rl_weights")
                return rlw if isinstance(rlw, dict) else None
            except (json.JSONDecodeError, TypeError):
                pass
        return None

    # ── Transcripts (v1.1.0) ─────────────────────────────

    @with_retry_on_busy()
    @_require_conn
    def save_transcript(self, session_id: str, user_id: str, messages: List,
                        project: str = "default", profile: str = "default"):
        with self._lock:
            self._conn.execute("""
                INSERT INTO session_transcripts (session_id, user_id, project, profile, messages, updated_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(session_id) DO UPDATE SET
                    messages=excluded.messages, updated_at=datetime('now')
            """, (session_id, user_id, project, profile, json.dumps(messages, ensure_ascii=False)))
            self._maybe_commit()

    @with_retry_on_busy()
    @_require_conn
    def save_transcript_summary(self, session_id: str, summary: str,
                                key_decisions: List = None):
        with self._lock:
            # INSERT OR IGNORE then UPDATE, so a summary for a missing
            # transcript row is not silently lost (no bare UPDATE no-op)
            self._conn.execute("""
                INSERT OR IGNORE INTO session_transcripts
                (session_id, messages, updated_at)
                VALUES (?, '[]', datetime('now'))
            """, (session_id,))
            self._conn.execute("""
                UPDATE session_transcripts
                SET compressed_summary=?, key_decisions=?,
                    updated_at=datetime('now')
                WHERE session_id=?
            """, (summary, json.dumps(key_decisions or []), session_id))
            self._maybe_commit()

    @_require_conn
    def _get_recent_session_count(self, user_id: str, days: int = 7) -> int:
        """Count distinct sessions for a user in the last N days."""
        try:
            cursor = self._conn.execute(
                "SELECT COUNT(DISTINCT session_id) FROM session_transcripts "
                "WHERE user_id=? AND created_at >= datetime('now', ?)",
                (user_id, f"-{days} days")
            )
            return cursor.fetchone()[0]
        except Exception:
            return 0

    @_require_conn
    def search_transcripts(self, query: str, user_id: str = None,
                           project: str = None, limit: int = 5) -> List[Dict]:
        # Escape LIKE wildcards to prevent unintended broad matching
        safe_query = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        where_parts = []
        params = []
        if user_id:
            where_parts.append("user_id=?")
            params.append(user_id)
        if project:
            where_parts.append("project=?")
            params.append(project)
        w = " WHERE " + " AND ".join(where_parts) + " AND " if where_parts else " WHERE "
        sql = f"SELECT * FROM session_transcripts{w}(messages LIKE ? ESCAPE '\\' OR compressed_summary LIKE ? ESCAPE '\\')"
        params += [f"%{safe_query}%", f"%{safe_query}%"]
        sql += f" ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    # ── Reflection ───────────────────────────────────────

    @with_retry_on_busy()
    @_require_conn
    def save_reflection(self, data: dict):
        with self._lock:
            ref = data.get("reflection", {})
            self._conn.execute(
                """INSERT OR REPLACE INTO reflections
                (id, user_id, platform, source_episodic_ids,
                 key_insights, user_preferences, procedural_rules,
                 new_knowledge, importance_scores, forget_suggestions,
                 confidence, meta, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    data.get("id", ""),
                    data.get("user_id", ""),
                    data.get("platform", "default"),
                    json.dumps(data.get("source_episodic_ids", [])),
                    json.dumps(ref.get("key_insights", [])),
                    json.dumps(ref.get("user_preferences", [])),
                    json.dumps(ref.get("procedural_rules", [])),
                    json.dumps(ref.get("new_knowledge", [])),
                    json.dumps(ref.get("importance_scores", {})),
                    json.dumps(ref.get("forget_suggestions", [])),
                    ref.get("confidence", 0.0),
                    json.dumps(data.get("meta", {})),
                    data.get("created_at", datetime.now(timezone.utc).isoformat()),
                ),
            )
            self._maybe_commit()

    # ── Daily reflection quota (P5-B): per-(user, date) counters ──

    @with_retry_on_busy()
    @_require_conn
    def get_daily_reflection_count(self, user_id: str, date: str) -> int:
        """Return how many reflections this user has consumed on the given UTC
        date (ISO yyyy-mm-dd). Missing row → 0."""
        with self._lock:
            row = self._conn.execute(
                "SELECT count FROM reflection_daily_count WHERE user_id=? AND date=?",
                (user_id, date),
            ).fetchone()
            return int(row["count"]) if row else 0

    @with_retry_on_busy()
    @_require_conn
    def increment_daily_reflection_count(self, user_id: str, date: str) -> int:
        """Atomically increment and return the user's reflection count for the
        given UTC date. The row is created on first use within the day."""
        with self._lock:
            self._conn.execute(
                """INSERT INTO reflection_daily_count (user_id, date, count)
                   VALUES (?, ?, 1)
                   ON CONFLICT(user_id, date) DO UPDATE SET count = count + 1""",
                (user_id, date),
            )
            self._maybe_commit()
            row = self._conn.execute(
                "SELECT count FROM reflection_daily_count WHERE user_id=? AND date=?",
                (user_id, date),
            ).fetchone()
            return int(row["count"]) if row else 1

    @_require_conn
    def get_recent_episodic(self, user_id: str, count: int = 8,
                            profile: str = None) -> List[Dict]:
        where = "user_id=?"
        params = [user_id]
        if profile:
            where += " AND profile=?"
            params.append(profile)
        rows = self._conn.execute(
            f"SELECT id, user_id, title, status, steps, created_at, project, tags, session_id, profile "
            f"FROM task_memory WHERE {where} ORDER BY created_at DESC LIMIT ?",
            params + [count],
        ).fetchall()
        records = [dict(r) for r in rows]
        # Enrich with content summary from experience_memory for reflection engine
        # M-R8 fix: batch all session lookups into a single WHERE ... IN query
        # instead of one query per record (N+1). Same (user, session) → summary
        # mapping for any session that may repeat across tasks.
        sids = sorted({r.get("session_id", "") for r in records if r.get("session_id")})
        exp_by_sid = {}
        if sids:
            placeholders = ",".join("?" * len(sids))
            exp_rows = self._conn.execute(
                f"SELECT session_id, summary FROM experience_memory "
                f"WHERE user_id=? AND session_id IN ({placeholders}) "
                f"ORDER BY created_at DESC, id ASC",
                [user_id] + sids,
            ).fetchall()
            for er in exp_rows:
                # P10 fix: previous code had no ORDER BY, so which row "won" the
                # map overwrite was unspecified (whichever SQLite returned last).
                # With explicit DESC ordering, the first row per (user, session)
                # is the most recent; keep it with first-wins semantics so the
                # reflection engine is guaranteed the freshest summary.
                exp_by_sid.setdefault(er["session_id"], er["summary"])
        for rec in records:
            sid = rec.get("session_id", "")
            if sid and sid in exp_by_sid:
                rec["content"] = exp_by_sid[sid]
            else:
                rec["content"] = rec.get("title", "")
        return records

    # ── Delete operations ──────────────────────────────────

    MEMORY_TABLES = {
        "user": "user_memory",
        "task": "task_memory",
        "experience": "experience_memory",
        "context": "context_memory",
        "knowledge": "knowledge_memory",
        "paper": "research_papers",
        "note": "research_notes",
        "reflection": "reflections",
        "transcript": "session_transcripts",
    }

    @with_retry_on_busy()
    @_require_conn
    def delete_memory(self, memory_type: str, memory_id: str) -> bool:
        """Delete a single memory record by type and ID."""
        table = self.MEMORY_TABLES.get(memory_type)
        if not table:
            raise ValueError(f"Unknown memory type: {memory_type}")
        id_col = "id"
        if memory_type == "user":
            # user_memory's key is (user_id, profile) — there is NO "id" column.
            # Routing user deletes through `id` would raise
            # "no such column: id". Match all profiles for the user; callers
            # that need a single profile should use delete_user_memories(profile=).
            id_col = "user_id"
        elif memory_type == "context":
            id_col = "session_id"
        elif memory_type == "transcript":
            id_col = "session_id"
        with self._lock:
            cursor = self._conn.execute(
                f"DELETE FROM {table} WHERE {id_col}=?", (memory_id,)
            )
            self._maybe_commit()
            return cursor.rowcount > 0

    @with_retry_on_busy()
    @_require_conn
    def delete_task(self, user_id: str, task_id: str) -> bool:
        """Delete a task by (user_id, task_id), reconstructing the stable key.

        B5/B6 closure: callers that know the pair no longer need to reproduce
        the (delimiter-ambiguous) composite id — this resolves the key the same
        way save_task/create_task do, so the row is always addressable.
        """
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM task_memory WHERE id=?",
                (stable_memory_key(user_id, task_id),),
            )
            self._maybe_commit()
            return cursor.rowcount > 0

    @with_retry_on_busy()
    @_require_conn
    def delete_user_memories(self, user_id: str, profile: str = None) -> Dict[str, int]:
        """Delete all memory records for a user. Returns counts per table."""
        results = {}
        # Tables that lack a profile column (reflections, session_transcripts)
        _NO_PROFILE_TABLES = {"reflections", "session_transcripts"}
        with self._lock:
            for key, table in self.MEMORY_TABLES.items():
                if profile and table not in _NO_PROFILE_TABLES:
                    cursor = self._conn.execute(
                        f"DELETE FROM {table} WHERE user_id=? AND profile=?",
                        (user_id, profile),
                    )
                else:
                    cursor = self._conn.execute(
                        f"DELETE FROM {table} WHERE user_id=?", (user_id,)
                    )
                results[key] = cursor.rowcount
            self._maybe_commit()
        return results

    @_require_conn
    def delete_expired(self, ttl_config: Dict[str, int]) -> Dict[str, int]:
        """Delete records older than TTL per type. Returns counts per table.

        Uses last_access_at if available, falls back to updated_at/created_at
        for legacy records created before the last_access_at field was added.
        """
        # Fallback timestamp columns per table (used when last_access_at is
        # absent or empty). Every table in MEMORY_TABLES must have an entry so
        # the delete never references a non-existent column.
        _FALLBACK_TS = {
            "user_memory": "last_updated",
            "task_memory": "updated_at",
            "context_memory": "updated_at",
            "knowledge_memory": "updated_at",
            "research_papers": "created_at",
            "experience_memory": "created_at",
            "research_notes": "updated_at",
            "reflections": "created_at",
            "session_transcripts": "updated_at",
        }
        results = {}
        with self._lock:
            for key, days in ttl_config.items():
                if days <= 0:
                    continue
                table = self.MEMORY_TABLES.get(key)
                if not table:
                    continue
                # Discover actual columns present: some tables only have a
                # fallback timestamp column (no last_access_at), so we cannot
                # write a fixed CASE expression.
                cols = {r["name"] for r in self._conn.execute(
                    f"PRAGMA table_info({table})").fetchall()}
                fallback = _FALLBACK_TS.get(table, "")
                has_ts = fallback in cols
                if "last_access_at" in cols and has_ts:
                    cursor = self._conn.execute(
                        f"DELETE FROM {table} WHERE "
                        f"(CASE WHEN last_access_at = '' THEN {fallback} ELSE last_access_at END) "
                        f"< datetime('now', ?)",
                        (f"-{days} days",),
                    )
                elif "last_access_at" in cols:
                    cursor = self._conn.execute(
                        f"DELETE FROM {table} WHERE last_access_at != '' AND "
                        f"last_access_at < datetime('now', ?)",
                        (f"-{days} days",),
                    )
                elif has_ts:
                    cursor = self._conn.execute(
                        f"DELETE FROM {table} WHERE {fallback} < datetime('now', ?)",
                        (f"-{days} days",),
                    )
                else:
                    logger.warning(
                        "delete_expired: table %s has no last_access_at or "
                        "fallback timestamp column; skipping", table)
                    results[key] = 0
                    continue
                results[key] = cursor.rowcount
            self._maybe_commit()
        return results

    def close(self):
        if self._conn:
            lock_held = False
            try:
                if self._lock:
                    acquired = self._lock.acquire(timeout=10)
                    if not acquired:
                        logger.warning("close: lock acquire timed out, forcing close without checkpoint")
                    else:
                        lock_held = True
                if lock_held:
                    self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                    self._conn.execute("PRAGMA optimize")
            except Exception:
                pass
            finally:
                if lock_held:
                    try:
                        self._lock.release()
                    except RuntimeError:
                        pass
                self._conn.close()
                self._conn = None
                self._lock = None

    # ── Schema diagnostics ──────────────────────────────────────

    def check_migration_status(self) -> Dict[str, Any]:
        """Diagnostics: check migration status for debugging and reports"""
        if not self._conn:
            return {"schema_version": None, "tables": {}, "error": "not connected"}
        current_version = self._conn.execute(
            "PRAGMA user_version"
        ).fetchone()[0]
        result = {
            "schema_version": current_version,
            "latest_version": SCHEMA_VERSION,
            "tables": {},
        }
        for table in _PROFILE_TABLES:
            cursor = self._conn.execute(f"PRAGMA table_info({table})")
            columns = [row[1] for row in cursor.fetchall()]
            has_profile = "profile" in columns
            if has_profile:
                cursor = self._conn.execute(
                    f"SELECT COUNT(*) as total, "
                    f"SUM(CASE WHEN profile='default' THEN 1 ELSE 0 END) as default_count, "
                    f"COUNT(DISTINCT profile) as profile_count "
                    f"FROM {table}"
                )
                row = cursor.fetchone()
                result["tables"][table] = {
                    "has_profile": True,
                    "total_rows": row[0],
                    "default_rows": row[1] if row[1] is not None else 0,
                    "distinct_profiles": row[2],
                }
            else:
                result["tables"][table] = {"has_profile": False}
        return result

    # ── Memory state lifecycle ───────────────────────────

    @with_retry_on_busy()
    @_require_conn
    def save_memory_state(self, memory_type: str, memory_id: str, state: str,
                          reason: str = "", source: str = "system"):
        """Record a memory state transition (upsert on duplicate key)."""
        with self._lock:
            prev = self._conn.execute(
                "SELECT state FROM memory_states WHERE memory_type=? AND memory_id=? "
                "ORDER BY state_changed_at DESC LIMIT 1",
                (memory_type, memory_id)
            ).fetchone()
            previous = prev["state"] if prev else ""
            self._conn.execute(
                "INSERT INTO memory_states (memory_type, memory_id, state, reason, previous_state, source) "
                "VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(memory_type, memory_id) DO UPDATE SET "
                "state=excluded.state, reason=excluded.reason, "
                "previous_state=memory_states.state, state_changed_at=datetime('now')",
                (memory_type, memory_id, state, reason, previous, source)
            )
            self._maybe_commit()

    @with_retry_on_busy()
    @_require_conn
    def get_memory_state(self, memory_type: str, memory_id: str) -> str:
        """Return the current state of a memory record, defaulting to 'active'.

        UNIQUE(memory_type, memory_id) guarantees at most one row,
        so no ORDER BY/LIMIT is needed.
        """
        row = self._conn.execute(
            "SELECT state FROM memory_states WHERE memory_type=? AND memory_id=?",
            (memory_type, memory_id)
        ).fetchone()
        return row["state"] if row else "active"

    @_require_conn
    def get_memory_stats(self) -> Dict[str, Any]:
        """Aggregate memory counts by type and state for the health report."""
        stats = {}
        for mem_type in ("knowledge", "experience", "task", "context", "user", "paper"):
            row = self._conn.execute(
                "SELECT state, COUNT(*) as cnt FROM memory_states "
                "WHERE memory_type=? "
                "GROUP BY state ORDER BY cnt DESC",
                (mem_type,)
            ).fetchall()
            stats[mem_type] = {r["state"]: r["cnt"] for r in row}
            stats[mem_type].setdefault("active", 0)
            stats[mem_type].setdefault("stale", 0)
            stats[mem_type].setdefault("archived", 0)
        # 7-day growth: count records created in the last 7 days (from original tables, not state changes)
        growth_queries = {
            "knowledge": "SELECT COUNT(*) AS cnt FROM knowledge_memory WHERE created_at >= datetime('now', '-7 days')",
            "experience": "SELECT COUNT(*) AS cnt FROM experience_memory WHERE created_at >= datetime('now', '-7 days')",
            "task": "SELECT COUNT(*) AS cnt FROM task_memory WHERE created_at >= datetime('now', '-7 days')",
        }
        for mem_type, sql in growth_queries.items():
            row = self._conn.execute(sql).fetchone()
            stats[f"{mem_type}_7d_growth"] = row["cnt"] if row else 0
        return stats

    # ── Knowledge evolution (P2-1) ──────────────────────────

    @with_retry_on_busy()
    @_require_conn
    def save_evolution(self, source_id: str, target_id: str, relation_type: str,
                       confidence: float = 0.5, reason: str = "",
                       detection_method: str = "jaccard",
                       origin_agent: str = "", origin_session_id: str = "",
                       origin_turn: int = 0):
        """Record a knowledge evolution relationship.

        origin_agent / origin_session_id / origin_turn populate the provenance
        columns (migration v9) so evolution records can be traced back to the
        agent/session/turn that produced them. Default empty/0 keeps backward
        compatibility for callers that don't track provenance.
        """
        with self._lock:
            self._conn.execute(
                "INSERT INTO knowledge_evolution (source_id, target_id, relation_type, "
                "confidence, reason, detection_method, origin_agent, origin_session_id, origin_turn) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (source_id, target_id, relation_type, confidence, reason,
                 detection_method, origin_agent, origin_session_id, origin_turn)
            )
            self._maybe_commit()

    @_require_conn
    def get_evolution_chain(self, knowledge_id: str, limit: int = 10) -> List[Dict]:
        """Return evolution chain for a knowledge entry (both as source and target)."""
        rows = self._conn.execute(
            "SELECT * FROM knowledge_evolution WHERE source_id=? OR target_id=? "
            "ORDER BY created_at DESC LIMIT ?",
            (knowledge_id, knowledge_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]

    @_require_conn
    def count_evolution_for(self, knowledge_id: str) -> int:
        """Count evolution records touching a knowledge entry (source or target).

        H-3 fix: wraps the raw query memory_agent._get_flags used to run against
        the private `_conn` so DB access stays inside SqliteStore's locking /
        decorator discipline.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM knowledge_evolution "
                "WHERE source_id=? OR target_id=?",
                (knowledge_id, knowledge_id)
            ).fetchone()
            return int(row["cnt"]) if row else 0

    @_require_conn
    def count_reflections(self) -> int:
        """Count persisted reflection records.

        H-3 fix: wraps the raw query compute_autoreflection_score used to run
        against the private `_conn` so DB access stays behind the store API.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) as cnt FROM reflections"
            ).fetchone()
            return int(row["cnt"]) if row else 0

    @_require_conn
    def get_latest_reflection(self, user_id: str) -> Optional[Dict]:
        """Return the most recent reflection for a user, or None.

        V8-3/V8-9 fix: gives memory._query_archive_data a public store-API
        path to the latest reflection instead of raw _conn SQL, and scopes the
        lookup to the user so archives never leak another user's reflection.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT confidence, key_insights, new_knowledge FROM reflections "
                "WHERE user_id=? ORDER BY created_at DESC LIMIT 1",
                (user_id,),
            ).fetchone()
            if not row:
                return None
            return {
                "confidence": row["confidence"],
                "key_insights": row["key_insights"] or "",
                "new_knowledge": row["new_knowledge"] or "",
            }

class _TransactionContext:
    """Internal transaction context manager.

    Wraps BEGIN IMMEDIATE so a batch of saves is atomic. When batch-active,
    save_* methods defer their auto-commit so a later failure rolls back all
    earlier writes (fixes loss of atomicity from per-save commits).
    """

    def __init__(self, conn, lock, batch_setter=None):
        self.conn = conn
        self.lock = lock
        self._set_batch = batch_setter  # callable(True/False) or None

    def __enter__(self):
        self.lock.acquire()
        self.conn.execute("BEGIN IMMEDIATE TRANSACTION")
        if self._set_batch:
            self._set_batch(True)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if self._set_batch:
                self._set_batch(False)
            if exc_type is None:
                self.conn.commit()
            else:
                self.conn.rollback()
        finally:
            self.lock.release()

