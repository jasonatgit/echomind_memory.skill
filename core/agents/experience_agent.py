# EchoMind — Experience Memory Agent

import logging
from typing import Dict, List, Optional

from ..models.experience import ExperienceEntry

logger = logging.getLogger("MemoryAgent")


class ExperienceMemoryAgent:
    MAX_ITEMS = 5000  # prevent unbounded dict growth

    def _evict_oldest(self):
        """LRU eviction: remove oldest 10% when over MAX_ITEMS."""
        if len(self.store) <= self.MAX_ITEMS:
            return
        excess = len(self.store) - int(self.MAX_ITEMS * 0.9)
        for k in list(self.store.keys())[:excess]:
            del self.store[k]



    def __init__(self):
        self.store: Dict[str, ExperienceEntry] = {}

    def store_experience(self, user_id: str, task_id: str, task_type: str,
                        success: bool, steps: List[str], summary: str) -> str:
        entry = ExperienceEntry(
            user_id=user_id, task_type=task_type,
            success=success, steps_sequence=steps, summary=summary,
        )
        self.store[entry.id] = entry
        self._evict_oldest()
        return entry.id

    def find_similar_tasks(self, task_context: str, task_type: str, user_id: Optional[str] = None,
                           project: str = None, session_id: str = None,
                           tags: List[str] = None,
                           min_success_rate: float = 0.7, limit: int = 3) -> List[Dict]:
        similar = []
        for entry in self.store.values():
            if user_id and entry.user_id != user_id:
                continue
            if project and entry.project != project:
                continue
            if session_id and entry.session_id != session_id:
                continue
            if tags:
                entry_tags = entry.tags if isinstance(entry.tags, list) else []
                if not any(t in entry_tags for t in tags):
                    continue
            if entry.task_type != task_type:
                continue
            # CQ-1: bool/float comparison fix — Only filter explicit failures
            if not entry.success:
                continue
            if any(k in entry.summary.lower() for k in task_context.lower().split()[:3]):
                similar.append({
                    "id": entry.id, "summary": entry.summary,
                    "steps": entry.steps_sequence, "success": entry.success,
                    "frequency": entry.frequency,
                })
        similar.sort(key=lambda x: x["frequency"], reverse=True)
        return similar[:limit]