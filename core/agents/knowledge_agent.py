# EchoMind — Knowledge Memory Agent
# Fix: user_id 过滤改用 entry.user_id, 关键词匹配扩展至所有词, 添加倒排索引

import logging
import re
from typing import Dict, List, Set

from ..models.knowledge import KnowledgeEntry

logger = logging.getLogger("MemoryAgent")


class KnowledgeMemoryAgent:
    MAX_ITEMS = 5000

    def _evict_oldest(self):
        if len(self.store) <= self.MAX_ITEMS:
            return
        excess = len(self.store) - int(self.MAX_ITEMS * 0.9)
        for k in list(self.store.keys())[:excess]:
            del self.store[k]

    def __init__(self):
        self.store: Dict[str, KnowledgeEntry] = {}
        self._content_index: Dict[int, str] = {}
        # 倒排索引: {user_id → set(entry_ids)}
        self._user_index: Dict[str, Set[str]] = {}

    def _add_to_index(self, entry: KnowledgeEntry):
        uid = entry.user_id if entry.user_id else entry.metadata.get("user_id", "default")
        self._user_index.setdefault(uid, set()).add(entry.id)

    def _remove_from_index(self, entry_id: str):
        for uid, ids in list(self._user_index.items()):
            ids.discard(entry_id)
            if not ids:
                del self._user_index[uid]

    def search(self, query: str, domain: str = None, user_id: str = None,
               project: str = None, session_id: str = None,
               tags: List[str] = None, top_k: int = 5,
               profile: str = None) -> List[Dict]:
        results = []
        # 利用倒排索引快速定位候选
        if user_id and user_id in self._user_index:
            candidate_ids = self._user_index[user_id]
            candidates = [self.store[eid] for eid in candidate_ids if eid in self.store]
        else:
            candidates = list(self.store.values())

        # 过滤停用词，构建查询词集
        stop_words = {"the", "is", "are", "a", "an", "and", "or", "but", "in", "on",
                      "to", "for", "of", "with", "at", "from", "by", "that", "this",
                      "it", "as", "be", "was", "has", "have", "had", "not", "no"}
        q_words = [w.lower() for w in re.findall(r'\b[a-zA-Z]{2,}\b', query)
                   if w.lower() not in stop_words]
        if not q_words:
            q_words = [w for w in query.lower().split() if len(w) > 1][:3]

        for entry in candidates:
            # 过滤条件
            if user_id and entry.user_id not in (user_id, "default"):
                if entry.metadata.get("user_id") not in (user_id, None):
                    continue
            if project and entry.metadata.get("project") not in (project, None, ""):
                continue
            if profile and entry.metadata.get("profile") not in (profile, None, ""):
                continue
            if session_id and entry.metadata.get("session_id") not in (session_id, None, ""):
                continue
            if tags:
                entry_tags = entry.metadata.get("tags", [])
                if not isinstance(entry_tags, list):
                    entry_tags = []
                if not any(t in entry_tags for t in tags):
                    continue
            if domain and entry.metadata.get("category") != domain:
                continue

            # 关键词匹配打分
            meta_text = " ".join(
                str(v) for v in entry.metadata.values() if isinstance(v, str)
            )
            searchable = (entry.content + " " + meta_text).lower()

            if not q_words or not searchable:
                continue

            matched = sum(1 for w in q_words if w in searchable)
            if matched == 0:
                # 尝试精确子串匹配
                if query.lower() not in searchable:
                    continue
                relevance = 0.5
            else:
                relevance = min(0.5 + 0.1 * matched, 0.95)
                if query.lower() in entry.content.lower():
                    relevance = max(relevance, 0.85)

            results.append({"id": entry.id, "content": entry.content,
                            "metadata": entry.metadata, "relevance": relevance})

        results.sort(key=lambda x: x.get("relevance", 0), reverse=True)
        return results[:top_k]

    def search_all(self, domain: str = None, project: str = None,
                   user_id: str = None, profile: str = None) -> List[Dict]:
        """返回所有匹配条目（不作 query 匹配），用于 compact_knowledge 等场景。"""
        results = []
        for entry in self.store.values():
            if user_id and entry.user_id not in (user_id, "default"):
                continue
            if project and entry.metadata.get("project") not in (project, None, ""):
                continue
            if profile and entry.metadata.get("profile") not in (profile, None, ""):
                continue
            if domain and entry.metadata.get("category") != domain:
                continue
            results.append({
                "id": entry.id, "content": entry.content,
                "metadata": entry.metadata,
                "domain": entry.metadata.get("category", "general"),
            })
        return results

    def find_procedures(self, domain: str = None, project: str = None,
                        user_id: str = None, limit: int = 5) -> List[Dict]:
        """Find procedural knowledge (how-to) entries."""
        results = []
        for entry in self.store.values():
            if user_id and entry.user_id not in (user_id, "default"):
                continue
            if project and entry.metadata.get("project") not in (project, None, ""):
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
        content_hash = hash(content)
        if content_hash in self._content_index:
            existing_id = self._content_index[content_hash]
            existing_entry = self.store.get(existing_id)
            if existing_entry:
                existing_entry.metadata["access_count"] = (
                    existing_entry.metadata.get("access_count", 0) + 1
                )
                existing_entry.metadata["last_updated"] = metadata.get(
                    "last_updated", existing_entry.metadata.get("last_updated", "")
                )
                return existing_id
        for existing_id, existing_entry in self.store.items():
            if existing_entry.content == content:
                existing_entry.metadata["access_count"] = (
                    existing_entry.metadata.get("access_count", 0) + 1
                )
                existing_entry.metadata["last_updated"] = metadata.get(
                    "last_updated", existing_entry.metadata.get("last_updated", "")
                )
                self._content_index[content_hash] = existing_id
                return existing_id
        entry = KnowledgeEntry(
            content=content, metadata=metadata,
            user_id=metadata.get("user_id", "default"))
        self.store[entry.id] = entry
        self._content_index[content_hash] = entry.id
        self._add_to_index(entry)
        self._evict_oldest()
        return entry.id