# EchoMind — Knowledge Memory Agent

import logging
from typing import Dict, List

from ..models.knowledge import KnowledgeEntry

logger = logging.getLogger("MemoryAgent")


class KnowledgeMemoryAgent:
    MAX_ITEMS = 5000  # prevent unbounded dict growth

    def _evict_oldest(self):
        """LRU eviction: remove oldest 10% when over MAX_ITEMS."""
        if len(self.store) <= self.MAX_ITEMS:
            return
        excess = len(self.store) - int(self.MAX_ITEMS * 0.9)
        for k in list(self.store.keys())[:excess]:
            del self.store[k]



    def __init__(self):
        self.store: Dict[str, KnowledgeEntry] = {}

    def search(self, query: str, domain: str = None, user_id: str = None,
               project: str = None, session_id: str = None,
               tags: List[str] = None, top_k: int = 5) -> List[Dict]:
        results = []
        for entry in self.store.values():
            if user_id and not entry.id.startswith(user_id + ":"):
                continue
            if project and entry.metadata.get("project") != project:
                continue
            if session_id and entry.metadata.get("session_id") != session_id:
                continue
            if tags:
                entry_tags = entry.metadata.get("tags", [])
                if not isinstance(entry_tags, list):
                    entry_tags = []
                if not any(t in entry_tags for t in tags):
                    continue
            if domain and entry.metadata.get("category") != domain:
                continue
            # Search content + metadata text value
            meta_text = " ".join(
                str(v) for v in entry.metadata.values() if isinstance(v, str)
            )
            searchable = entry.content + " " + meta_text
            if query.lower() in searchable.lower() or any(
                w in searchable.lower() for w in query.split()[:2]
            ):
                relevance = 0.8 if query.lower() in entry.content.lower() else 0.5
                results.append({"id": entry.id, "content": entry.content,
                                "metadata": entry.metadata, "relevance": relevance})
        results.sort(key=lambda x: x.get("relevance", 0), reverse=True)
        return results[:top_k]

    def find_procedures(self, domain: str = None, project: str = None,
                        user_id: str = None, limit: int = 5) -> List[Dict]:
        """Find procedural knowledge (how-to) entries."""
        results = []
        for entry in self.store.values():
            if user_id and not entry.id.startswith(user_id + ":"):
                continue
            if project and entry.metadata.get("project") != project:
                continue
            if domain and entry.metadata.get("category") != domain:
                continue
            etype = entry.metadata.get("entry_type", "fact")
            if etype != "procedure":
                continue
            results.append({
                "id": entry.id,
                "domain": entry.metadata.get("category", "general"),
                "content": entry.content,
                "prerequisites": entry.metadata.get("prerequisites", []),
                "output_template": entry.metadata.get("output_template", ""),
                "project": entry.metadata.get("project", "default"),
                "trust_score": entry.metadata.get("trust_score", 0.5),
            })
        return results[:limit]


    def add_document(self, content: str, metadata: Dict) -> str:
        entry = KnowledgeEntry(content=content, metadata=metadata)
        self.store[entry.id] = entry
        self._evict_oldest()
        return entry.id