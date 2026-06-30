# EchoMind — Experience Memory Agent
# Fix: add inverted index for faster search

import logging
import hashlib
from typing import Dict, List, Optional, Set

from ..models.experience import ExperienceEntry

logger = logging.getLogger("MemoryAgent")


class ExperienceMemoryAgent:
    MAX_ITEMS = 5000  # prevent unbounded dict growth

    def _evict_oldest(self):
        """LRU eviction: remove oldest 10% when over MAX_ITEMS."""
        if len(self.store) <= self.MAX_ITEMS:
            return
        excess = len(self.store) - int(self.MAX_ITEMS * 0.9)
        evicted_keys = list(self.store.keys())[:excess]
        for k in evicted_keys:
            entry = self.store.get(k)
            if entry:
                # Remove from index
                self._user_index.get(entry.user_id, set()).discard(k)
                self._type_index.get(entry.task_type, set()).discard(k)
            del self.store[k]

    def __init__(self):
        self.store: Dict[str, ExperienceEntry] = {}
        self._summary_index: Dict[int, str] = {}
        # Inverted index
        self._user_index: Dict[str, Set[str]] = {}
        self._type_index: Dict[str, Set[str]] = {}

    def _index_entry(self, entry: ExperienceEntry):
        self._user_index.setdefault(entry.user_id, set()).add(entry.id)
        self._type_index.setdefault(entry.task_type, set()).add(entry.id)

    def store_experience(self, user_id: str, task_id: str, task_type: str,
                        success: bool, steps: List[str], summary: str,
                        project: str = "default", session_id: str = "",
                        session_title: str = "", tags: List[str] = None,
                        profile: str = "default") -> str:
        summary_hash = int(hashlib.md5(f"{user_id}:{summary}".encode()).hexdigest(), 16) % (2**63 - 1)
        if summary_hash in self._summary_index:
            existing_id = self._summary_index[summary_hash]
            existing_entry = self.store.get(existing_id)
            if existing_entry and existing_entry.user_id == user_id and existing_entry.summary == summary:
                existing_entry.frequency += 1
                return existing_id
        # Fallback: linear scan for hash collisions
        for eid, entry in self.store.items():
            if entry.user_id == user_id and entry.summary == summary:
                self._summary_index[summary_hash] = eid
                entry.frequency += 1
                return eid
        entry = ExperienceEntry(
            user_id=user_id, task_id=task_id, task_type=task_type,
            success=success, steps_sequence=steps, summary=summary,
            project=project, session_id=session_id,
            session_title=session_title, tags=tags or [],
            profile=profile,
        )
        self.store[entry.id] = entry
        self._summary_index[summary_hash] = entry.id
        self._index_entry(entry)
        self._evict_oldest()
        return entry.id

    def find_similar_tasks(self, task_context: str, task_type: str, user_id: Optional[str] = None,
                           project: str = None, session_id: str = None,
                           tags: List[str] = None,
                           min_success_rate: float = 0.7, limit: int = 3,
                           profile: str = None) -> List[Dict]:
        # Use inverted index to quickly locate candidates
        candidate_ids = set(self.store.keys())
        if user_id and user_id in self._user_index:
            candidate_ids &= self._user_index[user_id]
        if task_type and task_type in self._type_index:
            candidate_ids &= self._type_index[task_type]

        similar = []
        for eid in candidate_ids:
            entry = self.store.get(eid)
            if not entry:
                continue
            if project and entry.project != project:
                continue
            if profile and entry.profile != profile:
                continue
            if session_id and entry.session_id != session_id:
                continue
            if tags:
                entry_tags = entry.tags if isinstance(entry.tags, list) else []
                if not any(t in entry_tags for t in tags):
                    continue
            # Filter by min_success_rate: skip failed entries when threshold > 0.5
            if min_success_rate > 0.5 and not entry.success:
                continue
            from ..lang_utils import tokenize as adaptive_tokenize, detect_language
            q_tokens = adaptive_tokenize(task_context)
            n_take = 10 if detect_language(task_context) == "zh" else 5
            if any(k in entry.summary.lower() for k in q_tokens[:n_take]):
                similar.append({
                    "id": entry.id, "summary": entry.summary,
                    "steps": entry.steps_sequence, "success": entry.success,
                    "frequency": entry.frequency,
                })
        similar.sort(key=lambda x: x["frequency"], reverse=True)
        return similar[:limit]