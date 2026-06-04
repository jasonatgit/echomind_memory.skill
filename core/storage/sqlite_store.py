# EchoMind Memory — SQLite Storage Layer (9 memory types)
# Fix: WAL Enable + write lock + threading import + datetime import

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DB_DIR = Path.home() / ".echomind"
DB_PATH = DB_DIR / "memory.db"


class SqliteStore:
    """SQLite Persistent storage — manage 9 memory data tables"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(DB_PATH)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._lock: Optional[threading.Lock] = None

    def connect(self):
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._lock = threading.Lock()
        logger.info(f"Connected to SQLite: {self.db_path} (WAL + busy_timeout=5000)")

    def ensure_tables(self):
        """Create complete 9 memory data tables"""
        if not self._conn:
            return
        with self._lock:
            self._conn.executescript("""
                -- 1. User memory: preferences, habits, interaction history
                CREATE TABLE IF NOT EXISTS user_memory (
                    user_id TEXT PRIMARY KEY,
                    preferences TEXT DEFAULT '{}',
                    habits TEXT DEFAULT '{}',
                    history TEXT DEFAULT '[]',
                    last_updated TEXT DEFAULT (datetime('now')),
                    version INTEGER DEFAULT 1
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
                    session_id TEXT DEFAULT '',
                    session_title TEXT DEFAULT '',
                    tags TEXT DEFAULT '[]',
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
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
                    session_id TEXT DEFAULT '',
                    session_title TEXT DEFAULT '',
                    tags TEXT DEFAULT '[]',
                    created_at TEXT DEFAULT (datetime('now')),
                    frequency INTEGER DEFAULT 1
                );

                -- 4. Context memory: conversation context, token count, session ID、Platform source
                CREATE TABLE IF NOT EXISTS context_memory (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT,
                    messages TEXT DEFAULT '[]',
                    token_count INTEGER DEFAULT 0,
                    platform TEXT DEFAULT 'default',
                    project TEXT DEFAULT 'default',
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
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
                    session_id TEXT DEFAULT '',
                    session_title TEXT DEFAULT '',
                    tags TEXT DEFAULT '[]',
                    user_id TEXT DEFAULT 'default',
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
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
                    user_id TEXT DEFAULT 'default',
                    created_at TEXT DEFAULT (datetime('now'))
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
                    messages TEXT,
                    compressed_summary TEXT DEFAULT '',
                    key_decisions TEXT DEFAULT '[]',
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now'))
                );

                -- index
                CREATE INDEX IF NOT EXISTS idx_task_user ON task_memory(user_id);
                CREATE INDEX IF NOT EXISTS idx_task_project ON task_memory(project);
                CREATE INDEX IF NOT EXISTS idx_task_updated ON task_memory(updated_at);
                CREATE INDEX IF NOT EXISTS idx_experience_user ON experience_memory(user_id);
                CREATE INDEX IF NOT EXISTS idx_experience_project ON experience_memory(project);
                CREATE INDEX IF NOT EXISTS idx_context_user ON context_memory(user_id);
                CREATE INDEX IF NOT EXISTS idx_knowledge_domain ON knowledge_memory(domain);
                CREATE INDEX IF NOT EXISTS idx_knowledge_user ON knowledge_memory(user_id);
                CREATE INDEX IF NOT EXISTS idx_knowledge_project ON knowledge_memory(project);
                CREATE INDEX IF NOT EXISTS idx_research_domain ON research_papers(domain);
                CREATE INDEX IF NOT EXISTS idx_session_transcripts_user ON session_transcripts(user_id);
            """)
            self._conn.commit()
            self._migrate_existing_tables()
            logger.info("All 9 memory tables ensured")

    def _migrate_existing_tables(self):
        """Compatible with old table structure -- Auto-add missing columns"""
        # Note: called from ensure_tables() which holds self._lock.
        # threading.Lock is NOT reentrant -- do not re-acquire.
        try:
            ctx_cols = [r[1] for r in self._conn.execute("PRAGMA table_info(context_memory)").fetchall()]
            if "platform" not in ctx_cols:
                self._conn.execute("ALTER TABLE context_memory ADD COLUMN platform TEXT DEFAULT 'default'")
                self._conn.commit()
                logger.info("Migration: added platform column to context_memory")
        except Exception as e:
            logger.warning(f"Migration failed for context_memory: {e}")
        try:
            pk_info = self._conn.execute(
                "SELECT type FROM pragma_table_info('task_memory') WHERE name='id'"
            ).fetchone()
            if pk_info and pk_info[0].upper() == 'INTEGER':
                logger.info("Migrating task_memory: INTEGER -> TEXT primary key")
                self._conn.execute(
                    "CREATE TABLE IF NOT EXISTS task_memory_new ("
                    "id TEXT PRIMARY KEY,"
                    "user_id TEXT, title TEXT, status TEXT,"
                    "steps TEXT DEFAULT '[]', metadata TEXT DEFAULT '{}',"
                    "created_at TEXT DEFAULT (datetime('now')),"
                    "updated_at TEXT DEFAULT (datetime('now'))"
                    ")"
                )
                self._conn.execute("INSERT INTO task_memory_new SELECT * FROM task_memory")
                self._conn.execute("DROP TABLE task_memory")
                self._conn.execute("ALTER TABLE task_memory_new RENAME TO task_memory")
                self._conn.commit()
        except Exception:
            logger.debug("Migration skipped for current table structure")
    def load_all(self) -> Dict[str, Any]:
        return {
            "users": self.load_users(),
            "tasks": self.load_tasks(),
            "experiences": self.load_experiences(),
            "contexts": self.load_contexts(),
            "knowledge": self.load_knowledge(),
            "research_papers": self.load_research_papers(),
            "research_notes": self.load_research_notes(),
        }

    def load_users(self) -> List[Dict]:
        if not self._conn: return []
        rows = self._conn.execute("SELECT * FROM user_memory ORDER BY last_updated DESC").fetchall()
        return [{k: (json.loads(r[k]) if k in ('preferences','habits','history') else r[k])
                 for k in r.keys()} for r in rows]

    def load_tasks(self) -> List[Dict]:
        if not self._conn: return []
        rows = self._conn.execute("SELECT * FROM task_memory ORDER BY updated_at DESC").fetchall()
        return [{k: (json.loads(r[k]) if k in ('steps','metadata','tags') else r[k])
                 for k in r.keys()} for r in rows]

    def load_experiences(self) -> List[Dict]:
        if not self._conn: return []
        rows = self._conn.execute("SELECT * FROM experience_memory ORDER BY created_at DESC").fetchall()
        return [{k: (json.loads(r[k]) if k in ('steps_sequence','tags') else r[k])
                 for k in r.keys()} for r in rows]

    def load_contexts(self) -> List[Dict]:
        if not self._conn: return []
        rows = self._conn.execute("SELECT * FROM context_memory ORDER BY updated_at DESC").fetchall()
        return [{k: (json.loads(r[k]) if k in ('messages',) else r[k])
                 for k in r.keys()} for r in rows]

    def load_knowledge(self) -> List[Dict]:
        if not self._conn: return []
        rows = self._conn.execute("SELECT * FROM knowledge_memory ORDER BY updated_at DESC").fetchall()
        return [{k: (json.loads(r[k]) if k in ('metadata','prerequisites','tags') else r[k])
                 for k in r.keys()} for r in rows]

    def load_research_papers(self, domain: str = None, project: str = None,
                             user_id: str = None, limit: int = 100) -> List[Dict]:
        if not self._conn: return []
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
        return [{k: (json.loads(r[k]) if k in ('authors','keywords','key_points','metadata') else r[k])
                 for k in r.keys()} for r in rows]

    def load_research_notes(self, user_id: str = None, project: str = None) -> List[Dict]:
        if not self._conn: return []
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
        return [{k: (json.loads(r[k]) if k in ('linked_papers','tags') else r[k])
                 for k in r.keys()} for r in rows]

    # ═══════════════════════════════════════════════════
    # SAVE
    # ═══════════════════════════════════════════════════


    def _merge_platform_prefs(self, existing_prefs, platform_prefs, platform):
        """Merge platform-specific preferences into existing structure."""
        merged = dict(existing_prefs) if existing_prefs else {}
        if "_default" not in merged:
            merged = {"_default": merged} if merged else {"_default": {}}
        merged[platform] = platform_prefs
        merged["_default"].update(platform_prefs)
        return merged
    def save_user(self, user_id: str, preferences: Dict = None, habits: Dict = None,
                  history: List = None, version: int = 1, platform: str = None):
        if not self._conn: return
        with self._lock:
            if platform:
                existing = self._get_user_raw(user_id)
                preferences = self._merge_platform_prefs(
                    existing.get("preferences", {}), preferences or {}, platform)
            else:
                preferences = {"_default": preferences or {}}
            self._conn.execute("""
                INSERT INTO user_memory (user_id, preferences, habits, history, last_updated, version)
                VALUES (?, ?, ?, ?, datetime('now'), ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    preferences=excluded.preferences, habits=excluded.habits,
                    history=excluded.history, last_updated=datetime('now'),
                    version=COALESCE(user_memory.version, 0) + 1
            """, (user_id,
                  json.dumps(preferences, ensure_ascii=False),
                  json.dumps(habits or {}, ensure_ascii=False),
                  json.dumps(history or [], ensure_ascii=False),
                  version))
            self._conn.commit()

    def _get_user_raw(self, user_id: str) -> Dict:
        if not self._conn: return {}
        row = self._conn.execute(
            "SELECT * FROM user_memory WHERE user_id = ?", (user_id,)
        ).fetchone()
        if not row: return {}
        result = {k: row[k] for k in row.keys()}
        for k in ('preferences', 'habits', 'history'):
            try:
                result[k] = json.loads(result[k])
            except (json.JSONDecodeError, TypeError, KeyError):
                result[k] = {} if k in ('preferences', 'habits') else []
        return result

    def save_task(self, user_id: str, task_id: str, title: str, status: str,
                  steps: List = None, metadata: Dict = None,
                  project: str = "default", session_id: str = "",
                  session_title: str = "", tags: List = None):
        if not self._conn: return
        with self._lock:
            task_pk = f"{user_id}:{task_id}"
            self._conn.execute("""
                INSERT INTO task_memory (id, user_id, title, status, steps, metadata,
                    project, session_id, session_title, tags, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status, steps=excluded.steps,
                    metadata=excluded.metadata, updated_at=datetime('now')
            """, (task_pk, user_id, title, status,
                  json.dumps(steps or []), json.dumps(metadata or {}),
                  project, session_id, session_title,
                  json.dumps(tags or [])))
            self._conn.commit()

    def save_experience(self, user_id: str, task_type: str, success: bool,
                        steps: List, summary: str, experience_id: str = None,
                        project: str = "default", session_id: str = "",
                        session_title: str = "", tags: List = None):
        if not self._conn: return
        with self._lock:
            eid = experience_id or f"{user_id}:{summary[:20]}:{int(datetime.now(timezone.utc).timestamp())}"
            self._conn.execute("""
                INSERT INTO experience_memory (id, user_id, task_type, success,
                    steps_sequence, summary, project, session_id, session_title, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    steps_sequence=excluded.steps_sequence,
                    summary=excluded.summary,
                    frequency=experience_memory.frequency + 1
            """, (eid, user_id, task_type, int(success), json.dumps(steps),
                  summary, project, session_id, session_title,
                  json.dumps(tags or [])))
            self._conn.commit()

    def save_context(self, session_id: str, user_id: str, messages: List,
                     token_count: int = 0, platform: str = "default",
                     project: str = "default"):
        if not self._conn: return
        with self._lock:
            self._conn.execute("""
                INSERT INTO context_memory (session_id, user_id, messages, token_count, platform, project, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(session_id) DO UPDATE SET
                    messages=excluded.messages, token_count=excluded.token_count,
                    platform=excluded.platform,
                    updated_at=datetime('now')
            """, (session_id, user_id, json.dumps(messages, ensure_ascii=False),
                  token_count, platform, project))
            self._conn.commit()

    def save_knowledge(self, knowledge_id: str, domain: str, content: str,
                       metadata: Dict = None, trust_score: float = 0.5,
                       entry_type: str = "fact", prerequisites: List = None,
                       output_template: str = "", user_id: str = "default",
                       project: str = "default", session_id: str = "",
                       session_title: str = "", tags: List = None):
        if not self._conn: return
        with self._lock:
            self._conn.execute("""
                INSERT INTO knowledge_memory (id, domain, content, metadata, trust_score,
                    entry_type, prerequisites, output_template, user_id, project,
                    session_id, session_title, tags, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(id) DO UPDATE SET
                    content=excluded.content, metadata=excluded.metadata,
                    trust_score=excluded.trust_score, updated_at=datetime('now')
            """, (knowledge_id, domain, content, json.dumps(metadata or {}), trust_score,
                  entry_type, json.dumps(prerequisites or []), output_template,
                  user_id, project, session_id, session_title,
                  json.dumps(tags or [])))
            self._conn.commit()

    def save_research_paper(self, paper_id: str, title: str, authors: List = None,
                            year: int = None, journal: str = None, abstract: str = "",
                            keywords: List = None, domain: str = "general",
                            paper_type: str = "theory", key_points: List = None,
                            importance_score: float = 0.5, metadata: Dict = None,
                            project: str = "default", user_id: str = "default"):
        if not self._conn: return
        with self._lock:
            self._conn.execute("""
                INSERT INTO research_papers (id, title, authors, year, journal,
                    abstract, keywords, domain, paper_type, key_points,
                    importance_score, metadata, project, user_id)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title, authors=excluded.authors, year=excluded.year,
                    journal=excluded.journal, abstract=excluded.abstract,
                    keywords=excluded.keywords, domain=excluded.domain,
                    paper_type=excluded.paper_type, key_points=excluded.key_points,
                    importance_score=excluded.importance_score
            """, (paper_id, title, json.dumps(authors or []), year, journal, abstract,
                  json.dumps(keywords or []), domain, paper_type, json.dumps(key_points or []),
                  importance_score, json.dumps(metadata or {}), project, user_id))
            self._conn.commit()

    def save_research_note(self, note_id: str, user_id: str, topic: str,
                           content: str, linked_papers: List = None, tags: List = None,
                           project: str = "default"):
        if not self._conn: return
        with self._lock:
            self._conn.execute("""
                INSERT INTO research_notes (id, user_id, topic, content, linked_papers, tags, project)
                VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    content=excluded.content,
                    linked_papers=excluded.linked_papers, tags=excluded.tags,
                    updated_at=datetime('now')
            """, (note_id, user_id, topic, content,
                  json.dumps(linked_papers or []), json.dumps(tags or []),
                  project))
            self._conn.commit()

    # ═══════════════════════════════════════════════════
    # SEARCH
    # ═══════════════════════════════════════════════════

    def search_context(self, user_id: str, query: str = None,
                        platform: str = None, limit: int = 3) -> List[Dict]:
        if not self._conn: return []
        where = "WHERE user_id = ?"
        params = [user_id]
        if platform:
            where += " AND platform = ?"
            params.append(platform)
        if query:
            where += " AND messages LIKE ?"
            params.append(f"%{query}%")
        rows = self._conn.execute(
            f"SELECT * FROM context_memory {where} ORDER BY updated_at DESC LIMIT ?",
            params + [limit]).fetchall()
        return [{k: (json.loads(r[k]) if k == "messages" else r[k])
                 for k in r.keys()} for r in rows]

    def save_rl_weights(self, user_id: str, weights: Dict[str, float]):
        if not self._conn: return
        with self._lock:
            self._conn.execute("""
                UPDATE user_memory SET preferences = json_set(
                    CASE WHEN json_type(preferences) IS NULL THEN '{}' ELSE preferences END,
                    '$.rl_weights', json(?)
                ), last_updated = datetime('now')
                WHERE user_id = ?
            """, (json.dumps(weights), user_id))
            self._conn.execute("""
                INSERT OR IGNORE INTO user_memory (user_id, preferences)
                VALUES (?, json_object('rl_weights', json(?)))
            """, (user_id, json.dumps(weights)))
            self._conn.commit()

    def load_rl_weights(self, user_id: str) -> Optional[Dict[str, float]]:
        if not self._conn: return None
        row = self._conn.execute(
            "SELECT preferences FROM user_memory WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row:
            try:
                prefs = json.loads(row["preferences"])
                return prefs.get("rl_weights")
            except (json.JSONDecodeError, TypeError):
                pass
        return None

    # ── Transcripts (v1.1.0) ─────────────────────────────

    def save_transcript(self, session_id: str, user_id: str, messages: List,
                        project: str = "default"):
        if not self._conn: return
        with self._lock:
            self._conn.execute("""
                INSERT INTO session_transcripts (session_id, user_id, project, messages, updated_at)
                VALUES (?, ?, ?, ?, datetime('now'))
                ON CONFLICT(session_id) DO UPDATE SET
                    messages=excluded.messages, updated_at=datetime('now')
            """, (session_id, user_id, project, json.dumps(messages, ensure_ascii=False)))
            self._conn.commit()

    def save_transcript_summary(self, session_id: str, summary: str,
                                key_decisions: List = None):
        if not self._conn: return
        with self._lock:
            self._conn.execute("""
                UPDATE session_transcripts
                SET compressed_summary=?, key_decisions=?,
                    updated_at=datetime('now')
                WHERE session_id=?
            """, (summary, json.dumps(key_decisions or []), session_id))
            self._conn.commit()

    def search_transcripts(self, query: str, user_id: str = None,
                           project: str = None, limit: int = 5) -> List[Dict]:
        if not self._conn: return []
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

    def save_reflection(self, data: dict):
        if not self._conn: return
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
            self._conn.commit()

    def get_recent_episodic(self, user_id: str, count: int = 8) -> List[Dict]:
        if not self._conn: return []
        rows = self._conn.execute(
            "SELECT id, user_id, title, status, steps, created_at, project, tags "
            "FROM task_memory WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, count),
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None