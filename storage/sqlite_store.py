import json
import sqlite3
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DB_DIR = Path.home() / ".echomind"
DB_PATH = DB_DIR / "memory.db"


class SqliteStore:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(DB_PATH)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self):
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        logger.info(f"Connected to SQLite: {self.db_path}")

    def ensure_tables(self):
        if not self._conn:
            return
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS user_memory (
                user_id TEXT PRIMARY KEY,
                preferences TEXT DEFAULT '{}',
                habits TEXT DEFAULT '{}',
                history TEXT DEFAULT '[]',
                last_updated TEXT DEFAULT (datetime('now')),
                version INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS task_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                task_id TEXT,
                title TEXT,
                status TEXT,
                steps TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                metadata TEXT DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS experience_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                task_type TEXT,
                success INTEGER,
                steps_sequence TEXT,
                summary TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                frequency INTEGER DEFAULT 1
            );
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
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS research_notes (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                topic TEXT NOT NULL,
                content TEXT DEFAULT '',
                linked_papers TEXT DEFAULT '[]',
                tags TEXT DEFAULT '[]',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );
        """)
        self._conn.commit()

    def save_user(self, user_id: str, data: Dict[str, Any]):
        if not self._conn:
            return
        self._conn.execute("""
            INSERT INTO user_memory (user_id, preferences, habits, history, last_updated, version)
            VALUES (?, ?, ?, ?, datetime('now'), 1)
            ON CONFLICT(user_id) DO UPDATE SET
                preferences=excluded.preferences, habits=excluded.habits,
                history=excluded.history, last_updated=datetime('now'),
                version=user_memory.version+1
        """, (user_id,
              json.dumps(data.get("preferences", {})),
              json.dumps(data.get("habits", {})),
              json.dumps(data.get("history", []))))
        self._conn.commit()

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        if not self._conn:
            return None
        row = self._conn.execute(
            "SELECT * FROM user_memory WHERE user_id = ?", (user_id,)
        ).fetchone()
        if not row:
            return None
        return {
            "user_id": row["user_id"],
            "preferences": json.loads(row["preferences"] or "{}"),
            "habits": json.loads(row["habits"] or "{}"),
            "history": json.loads(row["history"] or "[]"),
            "last_updated": row["last_updated"],
            "version": row["version"],
        }

    def save_task(self, user_id: str, task_id: str, title: str, status: str,
                  steps: List[Dict] = None, metadata: Dict = None):
        if not self._conn:
            return
        self._conn.execute("""
            INSERT INTO task_memory (user_id, task_id, title, status, steps, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, task_id, title, status,
              json.dumps(steps or []), json.dumps(metadata or {})))
        self._conn.commit()

    def save_experience(self, user_id: str, task_type: str, success: bool,
                        steps: List[str], summary: str):
        if not self._conn:
            return
        self._conn.execute("""
            INSERT INTO experience_memory (user_id, task_type, success, steps_sequence, summary)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, task_type, int(success), json.dumps(steps), summary))
        self._conn.commit()

    def save_research_paper(self, paper_id: str, title: str, authors: List[str],
                            year: Optional[int], journal: Optional[str],
                            abstract: str, keywords: List[str], domain: str,
                            paper_type: str, key_points: List[str],
                            importance_score: float, metadata: Dict):
        if not self._conn:
            return
        self._conn.execute("""
            INSERT INTO research_papers (id, title, authors, year, journal,
                abstract, keywords, domain, paper_type, key_points,
                importance_score, metadata)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET title=excluded.title,
                authors=excluded.authors, year=excluded.year, journal=excluded.journal,
                abstract=excluded.abstract, keywords=excluded.keywords,
                domain=excluded.domain, paper_type=excluded.paper_type,
                key_points=excluded.key_points, importance_score=excluded.importance_score
        """, (paper_id, title, json.dumps(authors), year, journal, abstract,
              json.dumps(keywords), domain, paper_type, json.dumps(key_points),
              importance_score, json.dumps(metadata)))
        self._conn.commit()

    def save_research_note(self, note_id: str, user_id: str, topic: str,
                           content: str, linked_papers: List[str], tags: List[str]):
        if not self._conn:
            return
        self._conn.execute("""
            INSERT INTO research_notes (id, user_id, topic, content, linked_papers, tags)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET content=excluded.content,
                linked_papers=excluded.linked_papers, tags=excluded.tags,
                updated_at=datetime('now')
        """, (note_id, user_id, topic, content,
              json.dumps(linked_papers), json.dumps(tags)))
        self._conn.commit()

    def get_research_papers(self, domain: str = None, limit: int = 10) -> List[Dict]:
        if not self._conn:
            return []
        if domain:
            rows = self._conn.execute(
                "SELECT * FROM research_papers WHERE domain = ? ORDER BY importance_score DESC LIMIT ?",
                (domain, limit)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM research_papers ORDER BY importance_score DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None