import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PostgresStore:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self._conn = None

    async def connect(self):
        try:
            import asyncpg
            self._conn = await asyncpg.connect(self.dsn)
            logger.info(f"Connected to PostgreSQL: {self.dsn}")
        except ImportError:
            logger.warning("asyncpg not installed, falling back to mock store")
            self._conn = None
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            self._conn = None

    async def ensure_tables(self):
        if not self._conn:
            return
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS user_memory (
                user_id VARCHAR(128) PRIMARY KEY,
                preferences JSONB DEFAULT '{}',
                habits JSONB DEFAULT '{}',
                history JSONB DEFAULT '[]',
                last_updated TIMESTAMPTZ DEFAULT NOW(),
                version INTEGER DEFAULT 1
            )
        """)
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS task_memory (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id VARCHAR(128),
                task_id VARCHAR(128),
                title TEXT,
                status VARCHAR(20),
                steps JSONB,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                metadata JSONB DEFAULT '{}'
            )
        """)
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS experience_memory (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id VARCHAR(128),
                task_type VARCHAR(64),
                success BOOLEAN,
                steps_sequence JSONB,
                summary TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                frequency INTEGER DEFAULT 1
            )
        """)

    async def save_user(self, user_id: str, data: Dict[str, Any]):
        if not self._conn:
            return
        await self._conn.execute("""
            INSERT INTO user_memory (user_id, preferences, habits, history, last_updated, version)
            VALUES ($1, $2::jsonb, $3::jsonb, $4::jsonb, NOW(), 1)
            ON CONFLICT (user_id) DO UPDATE SET
                preferences = $2::jsonb,
                habits = $3::jsonb,
                history = $4::jsonb,
                last_updated = NOW(),
                version = user_memory.version + 1
        """, user_id,
            json.dumps(data.get("preferences", {})),
            json.dumps(data.get("habits", {})),
            json.dumps(data.get("history", [])))

    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        if not self._conn:
            return None
        row = await self._conn.fetchrow(
            "SELECT * FROM user_memory WHERE user_id = $1", user_id
        )
        if not row:
            return None
        return {
            "user_id": row["user_id"],
            "preferences": row["preferences"] or {},
            "habits": row["habits"] or {},
            "history": row["history"] or [],
            "last_updated": row["last_updated"].isoformat() if row["last_updated"] else None,
            "version": row["version"],
        }

    async def save_task(self, user_id: str, task_id: str, title: str, status: str,
                        steps: List[Dict] = None, metadata: Dict = None):
        if not self._conn:
            return
        await self._conn.execute("""
            INSERT INTO task_memory (user_id, task_id, title, status, steps, metadata)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb)
        """, user_id, task_id, title, status,
            json.dumps(steps or []),
            json.dumps(metadata or {}))

    async def get_tasks_by_user(self, user_id: str, limit: int = 10) -> List[Dict]:
        if not self._conn:
            return []
        rows = await self._conn.fetch(
            "SELECT * FROM task_memory WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2",
            user_id, limit
        )
        return [dict(r) for r in rows]

    async def save_experience(self, user_id: str, task_type: str, success: bool,
                              steps: List[str], summary: str):
        if not self._conn:
            return
        await self._conn.execute("""
            INSERT INTO experience_memory (user_id, task_type, success, steps_sequence, summary)
            VALUES ($1, $2, $3, $4::jsonb, $5)
        """, user_id, task_type, success, json.dumps(steps), summary)

    async def get_experiences(self, user_id: str, limit: int = 10) -> List[Dict]:
        if not self._conn:
            return []
        rows = await self._conn.fetch(
            "SELECT * FROM experience_memory WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2",
            user_id, limit
        )
        return [dict(r) for r in rows]

    async def close(self):
        if self._conn:
            await self._conn.close()
            self._conn = None