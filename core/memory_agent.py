# echomind_memory.skill/memory_agent.py

import json
import uuid
import random
import re
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MemoryAgent")

from .models.context import ContextMessage, ContextMemory
from .models.task import TaskMemory
from .models.user import UserMemory
from .models.knowledge import KnowledgeEntry
from .models.experience import ExperienceEntry
from .models.research import ResearchPaper, ResearchNote
from .reflective_agent import ReflectiveAgent
from .agents import (
    ContextMemoryAgent, TaskMemoryAgent, UserMemoryAgent,
    KnowledgeMemoryAgent, ExperienceMemoryAgent, ResearchMemoryAgent,
)


class MemoryRecord(BaseModel):
    source: str
    content: str
    importance: float
    metadata: Dict[str, Any]


from .learning.rl_weight_optimizer import RLWeightOptimizer
from .storage.sqlite_store import SqliteStore


class MainMemoryAgent:
    def __init__(self, db_path: str = None, config_manager=None):
        self.context_agent = ContextMemoryAgent()
        self.task_agent = TaskMemoryAgent()
        self.user_agent = UserMemoryAgent()
        self.knowledge_agent = KnowledgeMemoryAgent()
        self.experience_agent = ExperienceMemoryAgent()
        self.research_agent = ResearchMemoryAgent()
        self.db = SqliteStore(db_path)

        from .config_manager import get_config_manager
        self.cfg = config_manager or get_config_manager()

        rl_config = self.cfg.get_section("rl")
        self.rl_optimizer = RLWeightOptimizer(
            initial_weights=rl_config.get("initial_weights", {
                "relevance": 0.4,
            }),
            learning_rate=rl_config.get("learning_rate", 0.07),
            decay_factor=rl_config.get("decay_factor", 0.97),
            max_buffer_size=rl_config.get("max_buffer_size", 50),
        )
        self._persistence_enabled = False
        self._store_count: dict = {}
        self._pending_reflection = False
        self._research_kw_cache = None

        ref_config = self.cfg.get_section("reflection")
        self.reflective = ReflectiveAgent(self.db, self, config=ref_config)

    def enable_persistence(self):
        self.db.connect()
        self.db.ensure_tables()
        self._persistence_enabled = True
        self._load_from_db()  # Load history on startup
        logger.info("SQLite persistence enabled (7 tables, 6 memory types loaded)")

    def _load_from_db(self):
        """Restore all memories from SQLite to memory agents."""
        all_data = self.db.load_all()
        loaded = {"users": 0, "tasks": 0, "experiences": 0, "contexts": 0,
                   "knowledge": 0, "papers": 0, "notes": 0}

        # 1. User memory
        for u in all_data.get("users", []):
            uid = u["user_id"]
            self.user_agent.store[uid] = UserMemory(
                user_id=uid, preferences=u["preferences"],
                habits=u["habits"], history=u["history"],
                version=u.get("version", 1))
            self.user_agent.cache[uid] = self.user_agent.store[uid]
            loaded["users"] += 1

        # 2. Task memory
        for t in all_data.get("tasks", []):
            task = TaskMemory(
                user_id=t["user_id"], project=t.get("project","default"),
                session_id=t.get("session_id",""), 
                session_title=t.get("session_title",""),
                task_id=t.get("id", ""),
                title=t.get("title",""), status=t.get("status","pending"),
                steps=t.get("steps",[]), tags=t.get("tags",[]))
            task.metadata = t.get("metadata", {})
            self.task_agent.store[t.get("id", "")] = task
            loaded["tasks"] += 1

        # 3. Experience memory
        for e in all_data.get("experiences", []):
            exp = ExperienceEntry(
                user_id=e.get("user_id",""), project=e.get("project","default"),
                session_id=e.get("session_id",""),
                session_title=e.get("session_title",""),
                task_type=e.get("task_type","default"),
                success=bool(e.get("success",0)),
                steps_sequence=e.get("steps_sequence",[]),
                summary=e.get("summary",""), tags=e.get("tags",[]))
            self.experience_agent.store[e.get("id","")] = exp
            loaded["experiences"] += 1

        # 4. Context memory（Restore most recent session）
        for c in all_data.get("contexts", []):
            messages = c.get("messages", [])
            for msg in messages:
                if isinstance(msg, dict) and "role" in msg:
                    self.context_agent.add_message(msg)
            loaded["contexts"] += 1

        # 5. Knowledge memory
        for k in all_data.get("knowledge", []):
            metadata = k.get("metadata", {})
            metadata.setdefault("project", k.get("project", "default"))
            metadata.setdefault("session_id", k.get("session_id", ""))
            metadata.setdefault("session_title", k.get("session_title", ""))
            metadata.setdefault("tags", k.get("tags", []))
            metadata.setdefault("entry_type", k.get("entry_type", "fact"))
            metadata.setdefault("prerequisites", k.get("prerequisites", []))
            metadata.setdefault("output_template", k.get("output_template", ""))
            if "category" not in metadata and "domain" in k:
                metadata["category"] = k["domain"]
            entry = KnowledgeEntry(
                content=k.get("content",""),
                metadata=metadata)
            entry.id = k.get("id", entry.id)
            self.knowledge_agent.store[entry.id] = entry
            loaded["knowledge"] += 1

        # 6. Research papers
        for p in all_data.get("research_papers", []):
            paper = ResearchPaper(
                id=p.get("id",""), user_id=p.get("user_id","default"),
                project=p.get("project","default"),
                title=p.get("title",""),
                authors=p.get("authors",[]), year=p.get("year"),
                journal=p.get("journal",""), abstract=p.get("abstract",""),
                keywords=p.get("keywords",[]), domain=p.get("domain","general"),
                paper_type=p.get("paper_type","theory"),
                key_points=p.get("key_points",[]),
                importance_score=p.get("importance_score",0.5))
            self.research_agent.papers[paper.id] = paper
            loaded["papers"] += 1

        # 7. Research notes
        for n in all_data.get("research_notes", []):
            note = ResearchNote(id=n.get("id",""), user_id=n.get("user_id",""),
                project=n.get("project","default"),
                topic=n.get("topic",""), content=n.get("content",""),
                linked_papers=n.get("linked_papers",[]),
                tags=n.get("tags",[]))
            self.research_agent.notes[note.id] = note
            loaded["notes"] += 1

        if sum(loaded.values()) > 0:
            logger.info(f"Loaded from DB: {loaded}")
        else:
            logger.info("Empty DB — fresh start")

        # 8. RL Weight restoration
        saved_weights = self.db.load_rl_weights("default")
        if saved_weights:
            self.rl_optimizer.weights = saved_weights
            self.rl_optimizer.ema_weights = saved_weights.copy()
            logger.info(f"RL weights restored: {saved_weights}")

    def disable_persistence(self):
        self._persistence_enabled = False
        if hasattr(self, 'db') and self.db:
            self.db.close()

    def is_persistence_enabled(self) -> bool:
        return self._persistence_enabled

    def clear_pending_reflection(self):
        self._pending_reflection = False

    def _extract_task_features(self, task_context: str) -> Dict[str, Any]:
        if self._research_kw_cache is None:
            domain_keywords = self.cfg.get("domain", "keywords", default={})
            research_keywords = []
            for domain_id, keywords in domain_keywords.items():
                if isinstance(keywords, dict):
                    research_keywords.extend(keywords.get("zh", []))
                    research_keywords.extend(keywords.get("en", []))
                elif isinstance(keywords, list):
                    research_keywords.extend(keywords)
            self._research_kw_cache = set(kw.lower() for kw in research_keywords)
        research_keywords = self._research_kw_cache
        features = {
            "is_complex": any(k in task_context.lower() for k in ["detailed", "in-depth", "comparative", "comprehensive"]),
            "has_history": any(k in task_context.lower() for k in ["last", "previous", "continue", "next", "previously done"]),
            "domain": "finance" if any(k in task_context.lower() for k in ["finance", "budget", "reimbursement", "investment"]) else "general",
            "task_type": "analysis" if any(k in task_context.lower() for k in ["analysis", "report"]) else "general",
            "requires_research": any(k in task_context.lower() for k in research_keywords),
            "requires_knowledge": any(k in task_context.lower() for k in
                ["knowledge", "documentation", "standard", "agreement", "knowledge", "documentation"]),
            "research_domain": self._detect_research_domain(task_context),
        }
        return features

    def _extract_task_tags(self, context: List[Dict]) -> List[str]:
        """Extract topic tags from conversation context via keyword heuristics."""
        topic_kw = self.cfg.get_section("topic_keywords") or {}
        if not topic_kw:
            return []
        combined = " ".join(m.get("content", "") for m in context).lower()
        matched = set()
        for tag, langs in topic_kw.items():
            if isinstance(langs, dict):
                all_kw = langs.get("zh", []) + langs.get("en", [])
            elif isinstance(langs, list):
                all_kw = langs
            else:
                continue
            if any(k.lower() in combined for k in all_kw):
                matched.add(tag)
        return list(matched)[:5]

    def _detect_research_domain(self, text: str) -> str:
        """Hybrid domain detection: keyword match → LLM semantic fallback.

        Keyword matching is fast and free — always tried first.
        If no keyword match and LLM is available, uses LLM for semantic
        domain detection (e.g. 'ML' → 'ai', 'rowing data' → custom domain).
        """
        domain_keywords = self.cfg.get("domain", "keywords", default={})
        t = text.lower()

        # Phase 1: fast keyword match
        for domain_id, keywords in domain_keywords.items():
            if isinstance(keywords, dict):
                all_kw = keywords.get("zh", []) + keywords.get("en", [])
            elif isinstance(keywords, list):
                all_kw = keywords
            else:
                continue
            if any(k.lower() in t for k in all_kw):
                return domain_id

        # Phase 2: LLM semantic fallback (only when keyword match fails)
        try:
            llm = self._get_llm_client()
            if llm is not None and llm.available:
                return self._llm_detect_domain(llm, text, domain_keywords)
        except Exception:
            logger.debug("LLM domain detection unavailable, falling back to keyword match")
            pass

        return self.cfg.get("domain", "default", default="general")

    def _llm_detect_domain(self, llm, text: str, domain_keywords: dict) -> str:
        """Use LLM to determine which domain best matches the text."""
        domain_list = "\n".join(
            f"- {did}: {kw.get('zh', kw)[:3] if isinstance(kw, dict) else kw[:3]}"
            for did, kw in domain_keywords.items()
        )
        prompt = (
            "Which research domain best matches this text? "
            "Reply with ONLY the domain ID from the list below.\n\n"
            f"Domains:\n{domain_list}\n\n"
            f"Text: {text[:300]}"
        )
        result = llm.chat(prompt, temperature=0, max_tokens=20).strip()
        for did in domain_keywords:
            if did in result:
                return did
        return self.cfg.get("domain", "default", default="general")

    _llm_client_cache = None

    def _get_llm_client(self):
        """Lazy-init via singleton factory (dedup: same client as hermes_provider)."""
        if self._llm_client_cache is None:
            from .llm_client import get_llm_client
            self._llm_client_cache = get_llm_client()
        return self._llm_client_cache

    def retrieve_for_task(self, task_context: str, user_id: str,
                         task_id: Optional[str] = None,
                         platform: Optional[str] = None,
                         project: str = "default",
                         session_id: str = "") -> Dict[str, Any]:
        logger.info(f"Retrieving memory for task: {task_context[:50]}...")
        features = self._extract_task_features(task_context)
        retrieved = {}

        retrieval_cfg = self.cfg.get_section("retrieval")
        exp_top_k = retrieval_cfg.get("experience_limit", 5)
        exp_min_rate = retrieval_cfg.get("experience_min_success_rate_initial", 0.7)
        context_limit = retrieval_cfg.get("context_limit", 2)
        research_top_k = retrieval_cfg.get("research_top_k", 5)

        retrieved["user"] = self.user_agent.get(user_id, platform=platform)

        # Always retrieve knowledge and experience (Bug fix: previously gated on rigid keywords)
        retrieved["knowledge"] = self.knowledge_agent.search(
            query=task_context, domain=features["domain"], user_id=user_id,
            project=project, session_id=session_id, top_k=5)
        retrieved["experience"] = self.experience_agent.find_similar_tasks(
            task_context=task_context, task_type=features["task_type"],
            user_id=user_id, project=project, session_id=session_id,
            min_success_rate=0.5, limit=5)
        if features["has_history"]:
            if task_id:
                retrieved["task_progress"] = self.task_agent.get_task_progress(task_id)
            else:
                retrieved["task_history"] = self.task_agent.get_recent_tasks(
                    user_id=user_id, task_type=features["task_type"],
                    project=project, limit=5)
        if features.get("requires_research"):
            retrieved["research"] = self.research_agent.search_papers(
                query=task_context, domain=features.get("research_domain"),
                user_id=user_id, project=project, top_k=research_top_k)

        if self._persistence_enabled:
            recent_contexts = self.db.search_context(user_id, platform=platform, limit=context_limit)
            if project != "default" and recent_contexts:
                recent_contexts = [c for c in recent_contexts if c.get("project", "default") == project]
            if recent_contexts:
                retrieved["context"] = recent_contexts

        scored = self._compute_importance(retrieved, task_context, user_id, platform, features)
        top_memories = sorted(scored, key=lambda x: x.importance, reverse=True)[:8]

        return {
            "working_memory": top_memories,
            "raw_memory_sources": retrieved,
            "task_features": features,
            "feedback_request": True,
            "retrieved_memories": top_memories,
        }


    def _compute_freshness_score(self, entry, source):
        """Compute time-decay freshness factor."""
        now = datetime.now(timezone.utc)
        last_verified = None
        if hasattr(entry, 'last_verified_at') and entry.last_verified_at:
            try:
                last_verified = datetime.fromisoformat(entry.last_verified_at)
            except (ValueError, TypeError):
                last_verified = now
        if isinstance(entry, dict):
            lv = entry.get("last_verified_at")
            if lv:
                try:
                    last_verified = datetime.fromisoformat(lv)
                except (ValueError, TypeError):
                    last_verified = now
            else:
                last_verified = now
        
        if last_verified:
            age_days = (now - last_verified).days
            half_life = getattr(entry, 'half_life_days', 90)
            if isinstance(entry, dict):
                half_life = entry.get("half_life_days", 90)
            return 0.5 ** (age_days / half_life)
        return 1.0

    def _compute_platform_bias(self, platform):
        """Platform-aware weight for cross-platform vs same-platform retrieval."""
        if not platform:
            return 1.0
        task_platform = getattr(self, '_current_platform', None)
        return 1.0 if task_platform == platform else 0.5

    def _compute_task_status_weight(self, task_status):
        """Weight based on task status: failed tasks are more relevant."""
        if task_status == "failed":
            return 1.3
        elif task_status == "completed":
            return 0.9
        return 1.0
    def _compute_importance(self, retrieved: Dict[str, Any], query: str,
                            user_id: str, platform: Optional[str] = None,
                            features: Dict[str, Any] = None) -> List[MemoryRecord]:
        research_domain = (features or {}).get("research_domain", "general")

        scored = []
        weights = self.rl_optimizer.get_current_weights()

        for source, memories in retrieved.items():
            if source == "user":
                user_mem = memories
                score = 0.8
                if user_mem.get("preferences", {}).get("response_style") == "concise":
                    score += 0.2 * weights["explicit_feedback"]
                scored.append(MemoryRecord(
                    source=source,
                    content=f"User preferences: {json.dumps(user_mem.get('preferences', {}), ensure_ascii=False)}",
                    importance=round(score, 3), metadata=user_mem,
                ))
                habits = user_mem.get("habits", {})
                if habits:
                    scored.append(MemoryRecord(
                        source=source,
                        content=f"User habits: {json.dumps(habits, ensure_ascii=False)}",
                        importance=round(score * 0.8, 3), metadata=habits,
                    ))

            elif source == "knowledge":
                for mem in memories:
                    relevance = mem["relevance"]
                    recency = 1.0
                    if "last_updated" in mem["metadata"]:
                        age = (datetime.now(timezone.utc) - datetime.fromisoformat(mem["metadata"]["last_updated"])).days
                        recency = max(0, 1 - age / 30)
                    trust = mem["metadata"].get("trust_score", 0.5)
                    # Freshness decay: older knowledge entries fade
                    created = mem.get("created_at") or mem["metadata"].get("created_at", "")
                    freshness = 1.0
                    if created:
                        try:
                            from datetime import datetime, timezone
                            age_days = (datetime.now(timezone.utc) - datetime.fromisoformat(created)).days
                            half_life = mem["metadata"].get("half_life_days", 90)
                            freshness = 0.5 ** (age_days / max(half_life, 1))
                        except Exception:
                            logger.debug("Failed to calculate freshness score")
                    # Domain boost: same-domain memories get +0.1
                    mem_domain = mem["metadata"].get("domain") or mem["metadata"].get("category", "")
                    domain_boost = 0.1 if (research_domain != "general" and mem_domain == research_domain) else 0
                    score = (relevance * weights["relevance"] + recency * weights["recency"] + trust * weights["trust_score"] + domain_boost) * freshness
                    scored.append(MemoryRecord(source=source, content=mem["content"], importance=round(score, 3), metadata=mem))

            elif source == "experience":
                for mem in memories:
                    recency_mult = self.cfg.get("retrieval", "recency_multiplier", 0.5)
                    score = 0.6 * weights["relevance"] + mem["frequency"] * weights["frequency"] + recency_mult * weights["recency"]
                    # P3-8: task status weighting
                    task_status = mem.get("metadata", {}).get("task_status", "")
                    if task_status == "failed": score *= 1.3
                    elif task_status == "completed": score *= 0.9
                    scored.append(MemoryRecord(source=source, content=mem["summary"], importance=round(score, 3), metadata=mem))

            elif source == "task_progress":
                scored.append(MemoryRecord(
                    source=source,
                    content=f"Task progress: {json.dumps(memories, ensure_ascii=False)}",
                    importance=0.9, metadata=memories,
                ))

            elif source == "task_history":
                for mem in memories:
                    scored.append(MemoryRecord(
                        source=source,
                        content=f"Previous task: {mem['title']} ({mem['status']})",
                        importance=0.6, metadata=mem,
                    ))

            elif source == "research":
                for mem in memories:
                    mem_paper_domain = mem.get("domain", "")
                    research_domain_boost = 0.15 if (research_domain != "general" and mem_paper_domain == research_domain) else 0
                    score = mem["relevance"] * weights["relevance"] + mem["importance_score"] * 0.3 + research_domain_boost
                    key_points_str = "; ".join(mem.get("key_points", [])[:3])
                    scored.append(MemoryRecord(
                        source=source,
                        content=f"[{mem.get('domain','general')}] {mem['title']}: {key_points_str}",
                        importance=round(score, 3), metadata=mem,
                    ))

            elif source == "context":
                for ctx in memories:
                    messages = ctx.get("messages", [])
                    if not messages:
                        continue
                    # Preserve full message structure — content is JSON array
                    ctx_platform = ctx.get("platform", "")
                    platform_mult = 1.0 if (not platform or ctx_platform == platform) else 0.5
                    scored.append(MemoryRecord(
                        source="context",
                        content=json.dumps(messages, ensure_ascii=False),
                        importance=round(0.7 * platform_mult, 3),
                        metadata={
                            "session_id": ctx.get("session_id", ""),
                            "platform": ctx_platform,
                            "messages": messages,
                            "token_count": ctx.get("token_count", 0),
                        },
                    ))

        return scored

    def search_transcripts(self, query: str, user_id: str = None,
                           project: str = None, limit: int = 5):
        if not self._persistence_enabled:
            return []
        return self.db.search_transcripts(query, user_id, project, limit)

    def compact_knowledge(self, domain: str = None, project: str = "default",
                         max_items: int = 50) -> int:
        """Merge redundant knowledge entries within same domain+project via LLM."""
        if not self._persistence_enabled:
            return 0
        import json
        knowledge = self.knowledge_agent.search("", domain=domain,
            project=project, top_k=max_items * 2)
        if len(knowledge) <= max_items:
            return 0

        # Group by domain, keep newest half, merge older half
        merged = 0
        domain_groups = {}
        for k in knowledge:
            d = k.get("domain", "general")
            domain_groups.setdefault(d, []).append(k)

        llm = self._get_llm_client()
        if not llm:
            return 0

        for d, items in domain_groups.items():
            if len(items) <= 10:
                continue
            items.sort(key=lambda x: x.get("trust_score", 0.5), reverse=True)
            keep = items[:len(items)//2]
            merge = items[len(items)//2:]
            prompt = f"Merge these {d} knowledge entries into a single concise summary (max 300 chars):\n"
            for m in merge:
                prompt += f"- {m.get('content','')[:200]}\n"
            try:
                summary = llm.chat(prompt).strip()[:500]
                if summary:
                    kid = f"compacted:{d}:{project}:{len(items)}"
                    self.db.save_knowledge(kid, d, summary, project=project,
                        entry_type="compacted", tags=[d])
                    merged += 1
            except Exception:
                logger.debug("Knowledge compaction failed, skipping")
        return merged

    def _cosine_prefilter(self, query: str, candidates: list,
                          text_key: str = "content", top_n: int = 20) -> list:
        """Pre-filter candidates via simple n-gram Jaccard similarity."""
        import re
        def tokenize(s):
            return set(re.findall(r'\b[a-zA-Z]{2,}\b', s.lower()))
        q_tokens = tokenize(query)
        if not q_tokens:
            return candidates[:top_n]
        scored = []
        for c in candidates:
            text = c.get(text_key, "")
            c_tokens = tokenize(text)
            if c_tokens:
                sim = len(q_tokens & c_tokens) / len(q_tokens | c_tokens)
                scored.append((c, sim))
            else:
                scored.append((c, 0))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [c for c, _ in scored[:top_n]]


    def store(self, user_id: str, task_id: str, context: List[Dict],
              task_status: str, success: bool = False, experience_summary: str = None,
              platform: str = None, title: str = None,
              project: str = "default", session_id: str = ""):
        """
        Store a task interaction and update all memory layers.
        """
        try:
            # Extract session title from first user message
            session_title = ""
            for msg in context:
                if msg.get("role") == "user" and not session_title:
                    session_title = msg.get("content", "")[:80]
                self.context_agent.add_message(msg)
            self.task_agent.create_task(user_id=user_id, task_id=task_id,
                                        title=title or "auto-task",
                                        steps=[{"step": "Initialize", "status": task_status}])
            task_tags = self._extract_task_tags(context) if hasattr(self, '_extract_task_tags') else []
            self._infer_user_preferences(context, user_id, platform=platform)

            # Extract task features（Shared by persistence and experience store）
            features = self._extract_task_features(
                " ".join(m.get("content","") for m in context if m.get("role")=="user"))

            if self._persistence_enabled:
                user_data = self.user_agent.get(user_id, platform=platform)
                self.db.save_user(user_id,
                    preferences=user_data.get("preferences", {}),
                    habits=user_data.get("habits", {}),
                    history=user_data.get("history", []),
                    platform=platform)
                self.db.save_task(user_id, task_id, title or "auto-task", task_status,
                                  steps=[{"step": "Initialize", "status": task_status}],
                                  project=project, session_id=session_id or "",
                                  session_title=session_title, tags=task_tags)
                # Save context memory (with platform tags)
                all_text = "".join(m.get("content", "") for m in context)
                chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', all_text))
                token_est = int(chinese_chars * 1.5 + (len(all_text) - chinese_chars) / 4)
                self.db.save_context(
                    session_id=f"{user_id}:{task_id}",
                    user_id=user_id,
                    messages=context,
                    token_count=token_est,
                    platform=platform or "default",
                    project=project)
                # If domain keywords found, save knowledge entry
                research_domain = features.get("research_domain", "general")
                if research_domain != "general":
                    best_content = ""
                    for msg in context:
                        if msg.get("role") == "assistant":
                            c = msg.get("content", "")
                            if len(c) > len(best_content):
                                best_content = c
                    knowledge_content = best_content[:2000] if best_content else (experience_summary or "Auto-extracted knowledge")
                    self.db.save_knowledge(
                        knowledge_id=f"{user_id}:{task_id}",
                        domain=research_domain,
                        content=knowledge_content,
                        metadata={"source": "task", "task_id": task_id},
                        project=project,
                        session_id=session_id or "",
                        session_title=session_title, tags=task_tags)

            if success or experience_summary:
                steps_from_context = [m["content"] for m in context if m["role"] != "system"]
                self.experience_agent.store_experience(
                    task_id=task_id, success=success, steps=steps_from_context,
                    summary=experience_summary or "System-generated experience summary",
                    user_id=user_id, task_type=features.get("task_type", "general"),
                )
                if self._persistence_enabled:
                    self.db.save_experience(user_id, features.get("task_type", "general"), success,
                                 steps_from_context,
                                 experience_summary or "System-generated experience summary",
                                 project=project,
                                 session_id=session_id or "",
                                 session_title=session_title, tags=task_tags)

            # Reflection trigger: per-user count, trigger after batch_size
            if self._persistence_enabled:
                self._store_count[user_id] = self._store_count.get(user_id, 0) + 1
                batch_size = self.reflective.config.get("batch_size", 8)
                if isinstance(batch_size, (list, tuple)):
                    batch_size = int(random.uniform(batch_size[0], batch_size[1]))
                if self._store_count[user_id] >= batch_size:
                    self._pending_reflection = True
                    self._store_count[user_id] = 0

        except Exception as e:
            logger.warning(f"store() failed: {e}")

    def get_recent_episodic(self, user_id: str, count: int = 8) -> List[Dict]:
        """Get recent N episodic records for ReflectiveAgent"""
        if self._persistence_enabled:
            return self.db.get_recent_episodic(user_id, count)
        return []

    def add_research_paper(self, title: str, authors: List[str] = None, year: int = None,
                           journal: str = None, abstract: str = "", keywords: List[str] = None,
                           domain: str = "general", paper_type: str = "theory",
                           key_points: List[str] = None, importance_score: float = 0.5) -> str:
        """Add research paper to memory and persist"""
        import uuid
        paper_id = str(uuid.uuid4())[:12]
        paper = ResearchPaper(
            id=paper_id, title=title, authors=authors or [], year=year,
            journal=journal or "", abstract=abstract, keywords=keywords or [],
            domain=domain, paper_type=paper_type, key_points=key_points or [],
            importance_score=importance_score)
        self.research_agent.add_paper(paper)
        if self._persistence_enabled:
            self.db.save_research_paper(
                paper_id=paper_id, title=title, authors=authors, year=year,
                journal=journal, abstract=abstract, keywords=keywords,
                domain=domain, paper_type=paper_type, key_points=key_points,
                importance_score=importance_score)
        logger.info(f"[Research] Added paper: {title}")
        return paper_id

    def add_research_note(self, user_id: str, topic: str, content: str,
                          linked_papers: List[str] = None, tags: List[str] = None) -> str:
        """Add research note to memory and persist"""
        import uuid
        note_id = str(uuid.uuid4())[:12]
        note = ResearchNote(id=note_id, user_id=user_id, topic=topic,
                            content=content, linked_papers=linked_papers or [],
                            tags=tags or [])
        self.research_agent.add_note(note)
        if self._persistence_enabled:
            self.db.save_research_note(note_id=note_id, user_id=user_id,
                                       topic=topic, content=content,
                                       linked_papers=linked_papers, tags=tags)
        logger.info(f"[Research] Added note: {topic}")
        return note_id

    def _infer_user_preferences(self, context, user_id, platform=None):
        """Infer user preferences from conversation."""
        prefs = self.user_agent.get(user_id).get("preferences", {})
        infer_cfg = self.cfg.get_section("inference")
        min_occ = infer_cfg.get("min_occurrence", 2)
        concise_kw = infer_cfg.get("keywords", {}).get("concise_response", ["brief","concise"])
        detailed_kw = infer_cfg.get("keywords", {}).get("detailed_type", ["type hint", "Optional[str]"])
        concise_code_kw = infer_cfg.get("keywords", {}).get("concise_code", ["concise","no comments"])

        all_content = " ".join(m["content"] for m in context)
        concise_count = sum(all_content.count(kw) for kw in concise_kw)
        if concise_count >= min_occ:
            prefs["response_style"] = "concise"
        if any(kw in all_content for kw in detailed_kw):
            prefs["code_style"] = "detailed"
        elif any(kw in all_content for kw in concise_code_kw):
            prefs["code_style"] = "concise"
        if prefs:
            self.user_agent.update(user_id, "preferences", prefs, source="implicit", platform=platform)

    def record_feedback(self, user_id: str, task_id: str, feedback: str, retrieved_memories: List[Dict]):
        if feedback not in ["positive", "negative"]:
            raise ValueError("feedback must be 'positive' or 'negative'")
        from .learning.rl_weight_optimizer import FeedbackRecord
        feedback_record = FeedbackRecord(
            user_id=user_id, task_id=task_id,
            retrieved_memories=retrieved_memories, user_feedback=feedback,
        )
        self.rl_optimizer.add_feedback(feedback_record)
        # Persist RL weights
        if self._persistence_enabled:
            self.db.save_rl_weights(user_id, self.rl_optimizer.weights)
        logger.info(f"User {user_id} gave {feedback} feedback on task {task_id}")

    def sync_to_code_project(self, project_root: str, user_id: str):
        from pathlib import Path
        echomind_dir = Path(project_root) / ".echomind"
        echomind_dir.mkdir(exist_ok=True)

        user_mem = self.user_agent.get(user_id)
        exp_mem = self.experience_agent.find_similar_tasks(
            task_context=f"Code style preferences: {user_mem.get('preferences', {}).get('code_style', 'standard')}",
            task_type="code_review", min_success_rate=0.6,
        )

        config = {
            "user_preferences": user_mem.get("preferences", {}),
            "user_habits": user_mem.get("habits", {}),
            "recent_code_experience": exp_mem[:3],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        (echomind_dir / "context.json").write_text(
            json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")

        summary = "=== EchoMind Memory summary ===\n"
        style = user_mem.get("preferences", {}).get("code_style")
        if style == "concise":
            summary += "▸ Your code style preferences: concise, no comments, short functions\n"
        elif style == "detailed":
            summary += "▸ Your code style preferences: detailed comments, docs-first, modular\n"
        for exp in exp_mem[:2]:
            summary += f"\n▸ You have successfully fixed:{exp['summary']}\n"
        for rp in list(self.research_agent.papers.values())[:3]:
            summary += f"\n▸ Research papers:{rp.title}（{rp.domain}）\n"
        (echomind_dir / "README.md").write_text(summary, encoding="utf-8")
        logger.info(f"Synced EchoMind memories to {echomind_dir}")

    def get_context(self) -> List[Dict]:
        return self.context_agent.get_context()

    def clear_context(self):
        self.context_agent.clear()