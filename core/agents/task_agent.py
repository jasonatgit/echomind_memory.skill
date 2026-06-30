# EchoMind — Task Memory Agent

import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional

from ..models.task import TaskMemory

logger = logging.getLogger("MemoryAgent")


class TaskMemoryAgent:
    MAX_ITEMS = 5000  # prevent unbounded dict growth

    def _evict_oldest(self):
        """LRU eviction: remove oldest 10% when over MAX_ITEMS."""
        if len(self.store) <= self.MAX_ITEMS:
            return
        excess = len(self.store) - int(self.MAX_ITEMS * 0.9)
        for k in list(self.store.keys())[:excess]:
            del self.store[k]


    
    def __init__(self):
        self.store: Dict[str, TaskMemory] = {}

    def create_task(self, user_id: str, task_id: str, title: str,
                     steps: List[Dict], profile: str = "default",
                     project: str = "default") -> str:
        task = TaskMemory(
            user_id=user_id, task_id=task_id, title=title, status="pending",
            steps=steps, profile=profile, project=project,
        )
        store_key = f"{user_id}:{task_id}"
        self.store[store_key] = task
        self._evict_oldest()
        logger.info(f"Task created: {store_key}")
        return task.id

    def update_step(self, task_id: str, step_index: int, status: str, result: str) -> bool:
        if task_id not in self.store:
            return False
        task = self.store[task_id]
        if step_index >= len(task.steps):
            return False
        task.steps[step_index]["status"] = status
        task.steps[step_index]["result"] = result
        task.updated_at = datetime.now(timezone.utc)
        return True

    def get_task_progress(self, task_id: str) -> Optional[Dict]:
        if task_id not in self.store:
            return None
        task = self.store[task_id]
        return {
            "status": task.status, "steps": task.steps,
            "title": task.title, "updated_at": task.updated_at.isoformat(),
        }

    def get_recent_tasks(self, user_id: str, task_type: str, project: str = None,
                        limit: int = 5, profile: str = None) -> List[Dict]:
        tasks = [t for t in self.store.values()
                 if t.user_id == user_id
                 and (not project or t.project == project)
                 and (not profile or t.profile == profile)]
        tasks.sort(key=lambda x: x.updated_at, reverse=True)
        return [{"task_id": t.task_id, "title": t.title, "status": t.status} for t in tasks[:limit]]