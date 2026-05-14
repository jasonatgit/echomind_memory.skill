# echomind_memory — SQLite 存储层（完整版：6 种记忆类型）
# 修复：新增 context_memory + knowledge_memory 表，所有 Agent 全量加载和保存

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DB_DIR = Path.home() / ".echomind"
DB_PATH = DB_DIR / "memory.db"


class SqliteStore:
    """SQLite 持久化存储 — 管理 6 种记忆的数据表"""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(DB_PATH)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self):
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        logger.info(f"Connected to SQLite: {self.db_path}")

    def ensure_tables(self):
        """创建完整的 7 张记忆数据表（user + task + experience + context + knowledge + research_papers + research_notes）"""
        if not self._conn:
            return
        self._conn.executescript("""
            -- 1. 用户记忆：偏好、习惯、交互历史
            CREATE TABLE IF NOT EXISTS user_memory (
                user_id TEXT PRIMARY KEY,
                preferences TEXT DEFAULT '{}',
                habits TEXT DEFAULT '{}',
                history TEXT DEFAULT '[]',
                last_updated TEXT DEFAULT (datetime('now')),
                version INTEGER DEFAULT 1
            );

            -- 2. 任务记忆：任务状态、步骤、元数据
            CREATE TABLE IF NOT EXISTS task_memory (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                title TEXT,
                status TEXT,
                steps TEXT DEFAULT '[]',
                metadata TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            -- 3. 经验记忆：成功/失败经验、步骤序列
            CREATE TABLE IF NOT EXISTS experience_memory (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                task_type TEXT,
                success INTEGER,
                steps_sequence TEXT DEFAULT '[]',
                summary TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                frequency INTEGER DEFAULT 1
            );

            -- 4. 上下文记忆：对话上下文、token 计数、会话 ID
            CREATE TABLE IF NOT EXISTS context_memory (
                session_id TEXT PRIMARY KEY,
                user_id TEXT,
                messages TEXT DEFAULT '[]',
                token_count INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            -- 5. 知识记忆：领域知识、结构化知识条目
            CREATE TABLE IF NOT EXISTS knowledge_memory (
                id TEXT PRIMARY KEY,
                domain TEXT DEFAULT 'general',
                content TEXT,
                metadata TEXT DEFAULT '{}',
                trust_score REAL DEFAULT 0.5,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            -- 6. 研究论文：学术论文元数据
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

            -- 7. 研究笔记：论文阅读笔记、研究线索
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

            -- 全文索引：加速关键词搜索
            CREATE INDEX IF NOT EXISTS idx_task_user ON task_memory(user_id);
            CREATE INDEX IF NOT EXISTS idx_task_updated ON task_memory(updated_at);
            CREATE INDEX IF NOT EXISTS idx_experience_user ON experience_memory(user_id);
            CREATE INDEX IF NOT EXISTS idx_context_user ON context_memory(user_id);
            CREATE INDEX IF NOT EXISTS idx_knowledge_domain ON knowledge_memory(domain);
            CREATE INDEX IF NOT EXISTS idx_research_domain ON research_papers(domain);
        """)
        self._conn.commit()
        # 对已存在的旧表做兼容性迁移
        self._migrate_existing_tables()
        logger.info("All 7 memory tables ensured (user, task, experience, context, knowledge, research_papers, research_notes)")

    def _migrate_existing_tables(self):
        """兼容旧表结构 —— 如果旧表缺少 id 列则添加"""
        try:
            old_task_cols = [r[1] for r in self._conn.execute("PRAGMA table_info(task_memory)").fetchall()]
            # 如果旧 task_memory 是用 INTEGER AUTOINCREMENT id，创造新的 TEXT id 表并迁移数据
            # 检测：看 id 是否为 INTEGER 类型
            pk_info = self._conn.execute("SELECT type FROM pragma_table_info('task_memory') WHERE name='id'").fetchone()
            if pk_info and pk_info[0].upper() == 'INTEGER':
                logger.info("Migrating task_memory: INTEGER → TEXT primary key")
                self._conn.execute("""
                    CREATE TABLE IF NOT EXISTS task_memory_new (
                        id TEXT PRIMARY KEY,
                        user_id TEXT, title TEXT, status TEXT,
                        steps TEXT DEFAULT '[]', metadata TEXT DEFAULT '{}',
                        created_at TEXT DEFAULT (datetime('now')),
                        updated_at TEXT DEFAULT (datetime('now'))
                    )
                """)
                self._conn.execute("INSERT INTO task_memory_new SELECT * FROM task_memory")
                self._conn.execute("DROP TABLE task_memory")
                self._conn.execute("ALTER TABLE task_memory_new RENAME TO task_memory")
                self._conn.commit()
        except Exception:
            pass

    # ═══════════════════════════════════════════════════
    # LOAD — 从 SQLite 加载全部记忆（启动时调用）
    # ═══════════════════════════════════════════════════

    def load_all(self) -> Dict[str, Any]:
        """加载所有持久化记忆数据，返回完整的记忆快照"""
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
        return [{k: (json.loads(r[k]) if k in ('steps','metadata') else r[k])
                 for k in r.keys()} for r in rows]

    def load_experiences(self) -> List[Dict]:
        if not self._conn: return []
        rows = self._conn.execute("SELECT * FROM experience_memory ORDER BY created_at DESC").fetchall()
        return [{k: (json.loads(r[k]) if k in ('steps_sequence',) else r[k])
                 for k in r.keys()} for r in rows]

    def load_contexts(self) -> List[Dict]:
        if not self._conn: return []
        rows = self._conn.execute("SELECT * FROM context_memory ORDER BY updated_at DESC").fetchall()
        return [{k: (json.loads(r[k]) if k in ('messages',) else r[k])
                 for k in r.keys()} for r in rows]

    def load_knowledge(self) -> List[Dict]:
        if not self._conn: return []
        rows = self._conn.execute("SELECT * FROM knowledge_memory ORDER BY updated_at DESC").fetchall()
        return [{k: (json.loads(r[k]) if k in ('metadata',) else r[k])
                 for k in r.keys()} for r in rows]

    def load_research_papers(self, domain: str = None, limit: int = 100) -> List[Dict]:
        if not self._conn: return []
        if domain:
            rows = self._conn.execute(
                "SELECT * FROM research_papers WHERE domain=? ORDER BY importance_score DESC LIMIT ?",
                (domain, limit)).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM research_papers ORDER BY importance_score DESC LIMIT ?",
                (limit,)).fetchall()
        return [{k: (json.loads(r[k]) if k in ('authors','keywords','key_points','metadata') else r[k])
                 for k in r.keys()} for r in rows]

    def load_research_notes(self) -> List[Dict]:
        if not self._conn: return []
        rows = self._conn.execute("SELECT * FROM research_notes ORDER BY updated_at DESC").fetchall()
        return [{k: (json.loads(r[k]) if k in ('linked_papers','tags') else r[k])
                 for k in r.keys()} for r in rows]

    # ═══════════════════════════════════════════════════
    # SAVE — 各记忆类型写入 SQLite
    # ═══════════════════════════════════════════════════

    def save_user(self, user_id: str, preferences: Dict = None, habits: Dict = None,
                  history: List = None, version: int = 1):
        if not self._conn: return
        self._conn.execute("""
            INSERT INTO user_memory (user_id, preferences, habits, history, last_updated, version)
            VALUES (?, ?, ?, ?, datetime('now'), ?)
            ON CONFLICT(user_id) DO UPDATE SET
                preferences=excluded.preferences, habits=excluded.habits,
                history=excluded.history, last_updated=datetime('now'),
                version=COALESCE(user_memory.version, 0) + 1
        """, (user_id,
              json.dumps(preferences or {}),
              json.dumps(habits or {}),
              json.dumps(history or []),
              version))
        self._conn.commit()

    def save_task(self, user_id: str, task_id: str, title: str, status: str,
                  steps: List = None, metadata: Dict = None):
        if not self._conn: return
        task_pk = f"{user_id}:{task_id}"
        self._conn.execute("""
            INSERT INTO task_memory (id, user_id, title, status, steps, metadata, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(id) DO UPDATE SET
                status=excluded.status, steps=excluded.steps,
                metadata=excluded.metadata, updated_at=datetime('now')
        """, (task_pk, user_id, title, status,
              json.dumps(steps or []), json.dumps(metadata or {})))
        self._conn.commit()

    def save_experience(self, user_id: str, task_type: str, success: bool,
                        steps: List, summary: str, experience_id: str = None):
        if not self._conn: return
        eid = experience_id or f"{user_id}:{summary[:20]}"
        self._conn.execute("""
            INSERT INTO experience_memory (id, user_id, task_type, success, steps_sequence, summary)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                steps_sequence=excluded.steps_sequence,
                summary=excluded.summary,
                frequency=experience_memory.frequency + 1
        """, (eid, user_id, task_type, int(success), json.dumps(steps), summary))
        self._conn.commit()

    def save_context(self, session_id: str, user_id: str, messages: List, token_count: int = 0):
        if not self._conn: return
        self._conn.execute("""
            INSERT INTO context_memory (session_id, user_id, messages, token_count, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(session_id) DO UPDATE SET
                messages=excluded.messages, token_count=excluded.token_count,
                updated_at=datetime('now')
        """, (session_id, user_id, json.dumps(messages, ensure_ascii=False), token_count))
        self._conn.commit()

    def save_knowledge(self, knowledge_id: str, domain: str, content: str,
                       metadata: Dict = None, trust_score: float = 0.5):
        if not self._conn: return
        self._conn.execute("""
            INSERT INTO knowledge_memory (id, domain, content, metadata, trust_score, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(id) DO UPDATE SET
                content=excluded.content, metadata=excluded.metadata,
                trust_score=excluded.trust_score, updated_at=datetime('now')
        """, (knowledge_id, domain, content, json.dumps(metadata or {}), trust_score))
        self._conn.commit()

    def save_research_paper(self, paper_id: str, title: str, authors: List = None,
                            year: int = None, journal: str = None, abstract: str = "",
                            keywords: List = None, domain: str = "general",
                            paper_type: str = "theory", key_points: List = None,
                            importance_score: float = 0.5, metadata: Dict = None):
        if not self._conn: return
        self._conn.execute("""
            INSERT INTO research_papers (id, title, authors, year, journal,
                abstract, keywords, domain, paper_type, key_points, importance_score, metadata)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title, authors=excluded.authors, year=excluded.year,
                journal=excluded.journal, abstract=excluded.abstract,
                keywords=excluded.keywords, domain=excluded.domain,
                paper_type=excluded.paper_type, key_points=excluded.key_points,
                importance_score=excluded.importance_score
        """, (paper_id, title, json.dumps(authors or []), year, journal, abstract,
              json.dumps(keywords or []), domain, paper_type, json.dumps(key_points or []),
              importance_score, json.dumps(metadata or {})))
        self._conn.commit()

    def save_research_note(self, note_id: str, user_id: str, topic: str,
                           content: str, linked_papers: List = None, tags: List = None):
        if not self._conn: return
        self._conn.execute("""
            INSERT INTO research_notes (id, user_id, topic, content, linked_papers, tags)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                content=excluded.content,
                linked_papers=excluded.linked_papers, tags=excluded.tags,
                updated_at=datetime('now')
        """, (note_id, user_id, topic, content,
              json.dumps(linked_papers or []), json.dumps(tags or [])))
        self._conn.commit()

    def search_context(self, user_id: str, query: str = None, limit: int = 3) -> List[Dict]:
        """搜索用户最近的会话上下文"""
        if not self._conn:
            return []
        where = "WHERE user_id = ?"
        params = [user_id]
        if query:
            where += " AND messages LIKE ?"
            params.append(f"%{query}%")
        rows = self._conn.execute(
            f"SELECT * FROM context_memory {where} ORDER BY updated_at DESC LIMIT ?",
            params + [limit]).fetchall()
        return [{k: (json.loads(r[k]) if k == "messages" else r[k])
                 for k in r.keys()} for r in rows]

    def save_rl_weights(self, user_id: str, weights: Dict[str, float]):
        """持久化 RL 优化器的权重到 user_memory 表"""
        if not self._conn:
            return
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
        """从 user_memory 加载 RL 权重"""
        if not self._conn:
            return None
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

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None