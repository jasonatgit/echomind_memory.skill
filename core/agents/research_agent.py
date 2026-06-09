# EchoMind — Research Memory Agent

import logging
from typing import Dict, List, Any

from ..models.research import ResearchPaper, ResearchNote

logger = logging.getLogger("MemoryAgent")


class ResearchMemoryAgent:
    def __init__(self):
        self.papers: Dict[str, ResearchPaper] = {}
        self.notes: Dict[str, ResearchNote] = {}
        # Domains are loaded dynamically from domain_keywords.yaml via ConfigManager.
        # Hardcoded ms_domains removed — use self._get_domains() instead.
        self._domain_cache = None

    def _get_domains(self) -> List[str]:
        """Load available research domains from ConfigManager (domain_keywords.yaml)."""
        if self._domain_cache is None:
            try:
                from ..config_manager import get_config_manager
                kw = get_config_manager().get("domain", "keywords", default={})
                self._domain_cache = list(kw.keys()) if kw else ["general"]
            except Exception:
                logger.debug("Failed to load domains from config, using default")
                self._domain_cache = ["general"]
        return self._domain_cache

    def add_paper(self, paper: ResearchPaper) -> str:
        self.papers[paper.id] = paper
        logger.info(f"[Research] Add paper: {paper.title}")
        return paper.id

    def search_papers(self, query: str, domain: str = None, user_id: str = None,
                      project: str = None, top_k: int = 5,
                      profile: str = None) -> List[Dict[str, Any]]:
        results = []
        q_lower = query.lower()
        for p in self.papers.values():
            if user_id and p.user_id != user_id:
                continue
            if project and p.project != project:
                continue
            if profile and p.profile != profile:
                continue
            if domain and p.domain != domain:
                continue
            relevance = 0.0
            t_lower = p.title.lower()
            k_lower = [kw.lower() for kw in p.keywords]
            a_lower = p.abstract.lower()
            q_words = [w for w in q_lower.split() if len(w) > 1]
            if q_lower in t_lower:
                relevance = 0.9
            elif any(kw in t_lower for kw in q_words):
                relevance = 0.85
            elif any(kw in q_lower for kw in k_lower):
                relevance = 0.8
            elif any(kw in a_lower for kw in q_words):
                relevance = 0.6
            elif any(kw in k_lower for kw in q_words):
                relevance = 0.5
            elif any(kw in p.keywords for kw in query.split()):
                relevance = 0.4
            if relevance > 0:
                results.append({
                    "id": p.id, "title": p.title, "abstract": p.abstract,
                    "keywords": p.keywords, "domain": p.domain,
                    "paper_type": p.paper_type, "key_points": p.key_points,
                    "importance_score": p.importance_score, "relevance": relevance,
                })
        results.sort(key=lambda x: x["relevance"] * x["importance_score"], reverse=True)
        return results[:top_k]

    def add_note(self, note: ResearchNote) -> str:
        self.notes[note.id] = note
        logger.info(f"[Research] Add note: {note.topic}")
        return note.id

    def search_notes(self, query: str, tags: List[str] = None, user_id: str = None,
                     project: str = None, top_k: int = 3,
                     profile: str = None) -> List[Dict]:
        results = []
        q_lower = query.lower()
        for n in self.notes.values():
            if user_id and n.user_id != user_id:
                continue
            if project and n.project != project:
                continue
            if profile and n.profile != profile:
                continue
            if tags and not any(t in n.tags for t in tags):
                continue
            relevance = 1.0 if q_lower in n.content.lower() else 0.3
            results.append({"id": n.id, "topic": n.topic, "content": n.content,
                            "tags": n.tags, "relevance": relevance})
        results.sort(key=lambda x: x["relevance"], reverse=True)
        return results[:top_k]

    def get_domain_overview(self, domain: str) -> List[Dict]:
        papers = [p for p in self.papers.values() if p.domain == domain]
        return [{"title": p.title, "keywords": p.keywords,
                 "paper_type": p.paper_type, "key_points": p.key_points}
                for p in papers[:10]]