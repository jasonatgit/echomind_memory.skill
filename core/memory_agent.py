# echomind_memory.skill/memory_agent.py

import json
import threading
import uuid
import random
import re
import hashlib
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger("MemoryAgent")
logger.setLevel(logging.INFO)

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
from .lang_utils import detect_language, get_features, get_inference_keywords, tokenize as adaptive_tokenize


class MainMemoryAgent:
    # ── Importance scoring constants ──
    _SCORE_USER_BASE = 0.8
    _SCORE_USER_PREF_BOOST = 0.2
    _SCORE_USER_HABITS_MULT = 0.8
    _SCORE_EXPERIENCE_BASE = 0.6
    _SCORE_TASK_PROGRESS = 0.9
    _SCORE_TASK_HISTORY = 0.6
    _SCORE_CONTEXT_BASE = 0.7
    _SCORE_CROSS_PLATFORM_MULT = 0.5
    _SCORE_DOMAIN_BOOST = 0.1
    _SCORE_RESEARCH_DOMAIN_BOOST = 0.15
    _SCORE_FAILED_MULT = 1.3
    _SCORE_COMPLETED_MULT = 0.9
    _SCORE_RECENCY_DECAY_DAYS = 30
    _SCORE_RESEARCH_IMPORTANCE_WEIGHT = 0.3
    _DECAY_HALF_LIFE = 69  # days — freshness = 2^(-days / half_life)
    _FRESHNESS_ARCHIVE_THRESHOLD = 0.1  # auto-exclude below this

    def __init__(self, db_path: str = None, config_manager=None):
        self.context_agent = ContextMemoryAgent(max_sessions=5)
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
        self._pending_reflection_event = threading.Event()
        self._pending_reflection = False
        self._store_lock = threading.Lock()
        self._research_kw_cache = None

        ref_config = self.cfg.get_section("reflection")
        self.reflective = ReflectiveAgent(self.db, self, config=ref_config)

    def enable_persistence(self):
        if self._persistence_enabled:
            return
        self.db.connect()
        self.db.ensure_tables()
        self._persistence_enabled = True
        self.context_agent.bind_store(self.db)
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
            uprofile = u.get("profile", "default")
            store_key = f"{uid}:{uprofile}"
            self.user_agent.store[store_key] = UserMemory(
                user_id=uid, profile=uprofile,
                preferences=u["preferences"],
                habits=u["habits"], history=u["history"],
                version=u.get("version", 1))
            self.user_agent.cache[store_key] = self.user_agent.store[store_key]
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
                profile=e.get("profile","default"),
                session_id=e.get("session_id",""),
                session_title=e.get("session_title",""),
                task_type=e.get("task_type","default"),
                success=bool(e.get("success",0)),
                steps_sequence=e.get("steps_sequence",[]),
                summary=e.get("summary",""), tags=e.get("tags",[]))
            exp.frequency = e.get("frequency", 1)  # restore persisted frequency
            self.experience_agent.store[e.get("id","")] = exp
            self.experience_agent._index_entry(exp)
            self.experience_agent._summary_index[int(hashlib.md5(f"{exp.user_id}:{exp.summary}".encode()).hexdigest(), 16) % (2**63 - 1)] = e.get("id","")
            loaded["experiences"] += 1

        # 4. Context memory（Restore with session isolation）
        for c in all_data.get("contexts", []):
            session_id = c.get("session_id", "")
            messages = c.get("messages", [])
            for msg in messages:
                if isinstance(msg, dict) and "role" in msg:
                    self.context_agent.add_message(msg, session_id=session_id)
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
                metadata=metadata,
                user_id=k.get("user_id", k.get("metadata", {}).get("user_id", "default")))
            entry.id = k.get("id", entry.id)
            self.knowledge_agent.store[entry.id] = entry
            self.knowledge_agent._add_to_index(entry)
            loaded["knowledge"] += 1

        # 6. Research papers
        for p in all_data.get("research_papers", []):
            paper = ResearchPaper(
                id=p.get("id",""), user_id=p.get("user_id","default"),
                project=p.get("project","default"),
                profile=p.get("profile","default"),
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
                profile=n.get("profile","default"),
                topic=n.get("topic",""), content=n.get("content",""),
                linked_papers=n.get("linked_papers",[]),
                tags=n.get("tags",[]))
            self.research_agent.notes[note.id] = note
            loaded["notes"] += 1

        if sum(loaded.values()) > 0:
            logger.info(f"Loaded from DB: {loaded}")
        else:
            logger.info("Empty DB — fresh start")

        # 8. RL Weight restoration — scan ALL users, use last found
        saved_weights = self.db.load_rl_weights("default")
        if loaded.get("users", 0) > 0 and self.user_agent.store:
            for store_key, u in list(self.user_agent.store.items()):
                w = self.db.load_rl_weights(u.user_id, profile=u.profile)
                if w:
                    saved_weights = w
        # If no user-specific weights found, try loading from user preferences JSON
        if not saved_weights and loaded.get("users", 0) > 0:
            for store_key, u in list(self.user_agent.store.items()):
                prefs = u.preferences if hasattr(u, 'preferences') else {}
                if isinstance(prefs, dict) and 'rl_weights' in prefs:
                    saved_weights = prefs['rl_weights']
                    logger.info("RL weights restored from preferences JSON for %s", u.user_id)
                    break
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

    def refresh_config(self):
        """Re-read captured config sections after cfg.on_reload event."""
        self._research_kw_cache = None
        try:
            self.reflective.config = self.cfg.get_section("reflection")
        except Exception:
            pass

    def clear_pending_reflection(self):
        self._pending_reflection_event = threading.Event()
        self._pending_reflection = False

    def _trigger_auto_reflection(self, user_id: str):
        """Schedule auto-reflection in background thread (non-blocking).
        Hermes path triggers via on_session_end hook instead."""
        import threading
        agent = self

        def _run():
            try:
                batch_size = agent.reflective.config.get("batch_size", 8)
                if isinstance(batch_size, (list, tuple)):
                    batch_size = int(random.uniform(batch_size[0], batch_size[1]))
                records = agent.get_recent_episodic(user_id, count=batch_size)
                min_records = agent.reflective.config.get("min_records", 6)
                if len(records) < min_records:
                    return
                from .llm_client import get_llm_client
                llm = get_llm_client()
                if llm and llm.available:
                    result = agent.reflective.reflect_with_llm(
                        records, user_id, "http", llm.chat)
                    if result:
                        logger.info(
                            "Auto-reflection: %d insights (confidence=%.2f)",
                            len(result.key_insights), result.confidence)
                        if agent._persistence_enabled:
                            agent.db.save_reflection({
                                "id": f"auto:{user_id}:{int(datetime.now(timezone.utc).timestamp())}",
                                "user_id": user_id,
                                "platform": "http",
                                "source_episodic_ids": [r.get("id", "") for r in records],
                                "reflection": {
                                    "key_insights": result.key_insights,
                                    "user_preferences": result.user_preferences,
                                    "procedural_rules": result.procedural_rules,
                                    "new_knowledge": result.new_knowledge,
                                    "importance_scores": result.importance_scores,
                                    "forget_suggestions": result.forget_suggestions,
                                    "confidence": result.confidence,
                                },
                                "meta": {"source": "auto_reflection", "record_count": len(records)},
                            })
            except Exception as e:
                logger.debug("Auto-reflection skipped: %s", e)

        threading.Thread(target=_run, daemon=True).start()

    @staticmethod
    def _flatten_domain_keywords(domain_entry) -> list:
        """Extract zh+en keyword lists from either flat or nested domain entry format."""
        if not isinstance(domain_entry, dict):
            return []
        if "keywords" in domain_entry and isinstance(domain_entry["keywords"], dict):
            inner = domain_entry["keywords"]
            return inner.get("zh", []) + inner.get("en", [])
        return domain_entry.get("zh", []) + domain_entry.get("en", [])

    def _extract_task_features(self, task_context: str) -> Dict[str, Any]:
        if self._research_kw_cache is None:
            domain_keywords = self.cfg.get("domain", "keywords", default={})
            research_keywords = []
            for domain_id, entry in domain_keywords.items():
                research_keywords.extend(self._flatten_domain_keywords(entry))
            self._research_kw_cache = set(kw.lower() for kw in research_keywords)
        research_keywords = self._research_kw_cache
        lang = detect_language(task_context)
        feat_cfg = get_features(lang)
        research_domain = self._detect_research_domain(task_context, lang)
        features = {
            "is_complex": any(k in task_context.lower() for k in feat_cfg.get("complex", [])),
            "has_history": any(k in task_context.lower() for k in feat_cfg.get("history", [])),
            "domain": research_domain,
            "task_type": "analysis" if any(k in task_context.lower() for k in feat_cfg.get("analysis", [])) else "general",
            "requires_research": any(k in task_context.lower() for k in research_keywords),
            "requires_knowledge": any(k in task_context.lower() for k in
                feat_cfg.get("knowledge", ["knowledge", "documentation", "standard", "agreement"])),
            "research_domain": research_domain,
            "language": lang,
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

    def _detect_research_domain(self, text: str, lang: str = None) -> str:
        """Hybrid domain detection: keyword match → LLM semantic fallback.

        Keyword matching is fast and free — always tried first.
        If no keyword match and LLM is available, uses LLM for semantic
        domain detection (e.g. 'ML' → 'ai', 'rowing data' → custom domain).
        """
        domain_keywords = self.cfg.get("domain", "keywords", default={})
        t = text.lower()

        # Phase 1: fast keyword match
        for domain_id, entry in domain_keywords.items():
            all_kw = self._flatten_domain_keywords(entry)
            if any(k.lower() in t for k in all_kw):
                return domain_id

        # Phase 2: LLM semantic fallback (only when keyword match fails)
        try:
            llm = self._get_llm_client()
            if llm is not None and llm.available:
                return self._llm_detect_domain(llm, text, domain_keywords, lang or "en")
        except Exception:
            logger.debug("LLM domain detection unavailable, falling back to keyword match")
            pass

        return self.cfg.get("domain", "default", default="general")

    def _llm_detect_domain(self, llm, text: str, domain_keywords: dict,
                           lang: str = "en") -> str:
        """Use LLM to determine which domain best matches the text."""
        domain_list = "\n".join(
            f"- {did}: {self._flatten_domain_keywords(kw)[:3]}"
            for did, kw in domain_keywords.items()
        )
        from .lang_utils import get_prompt
        prompt = get_prompt("domain_detect", lang,
                            domain_list=domain_list, text=text[:300])
        if not prompt:
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

    def _get_llm_client(self):
        """Lazy-init via thread-safe module-level singleton."""
        from .llm_client import get_llm_client
        return get_llm_client()

    def retrieve_for_task(self, task_context: str, user_id: str,
                         task_id: Optional[str] = None,
                         platform: Optional[str] = None,
                         project: str = "default",
                         session_id: str = "",
                         profile: str = "default") -> Dict[str, Any]:
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
            query=task_context, domain=features.get("research_domain", "general"), user_id=user_id,
            project=project, session_id=session_id, top_k=5,
            profile=profile)
        retrieved["experience"] = self.experience_agent.find_similar_tasks(
            task_context=task_context, task_type=features["task_type"],
            user_id=user_id, project=project, session_id=session_id,
            min_success_rate=0.5, limit=5,
            profile=profile)
        if features["has_history"]:
            if task_id:
                composite_id = f"{user_id}:{task_id}"
                retrieved["task_progress"] = self.task_agent.get_task_progress(composite_id)
            else:
                retrieved["task_history"] = self.task_agent.get_recent_tasks(
                    user_id=user_id, task_type=features["task_type"],
                    project=project, limit=5,
                    profile=profile)
        if features.get("requires_research"):
            retrieved["research"] = self.research_agent.search_papers(
                query=task_context, domain=features.get("research_domain"),
                user_id=user_id, project=project, top_k=research_top_k,
                profile=profile)

        if self._persistence_enabled:
            recent_contexts = self.db.search_context(user_id, platform=platform, limit=context_limit, profile=profile)
            if project != "default" and recent_contexts:
                recent_contexts = [c for c in recent_contexts if c.get("project", "default") == project]
            if recent_contexts:
                retrieved["context"] = recent_contexts

        scored = self._compute_importance(retrieved, task_context, user_id, platform, features)
        top_memories = sorted(scored, key=lambda x: x.importance, reverse=True)[:8]
        confidence = (sum(m.importance for m in top_memories)
                      / max(len(top_memories), 1))

        # Update last_access_at for retrieved records so freshness reflects true access time
        if self._persistence_enabled:
            self._update_last_access_for_retrieved(retrieved, user_id)

        return {
            "working_memory": top_memories,
            "raw_memory_sources": retrieved,
            "task_features": features,
            "feedback_request": True,
            "retrieved_memories": top_memories,
            "confidence_score": float(confidence),
            "user": retrieved.get("user", {}),
        }


    def _compute_importance(self, retrieved: Dict[str, Any], query: str,
                            user_id: str, platform: Optional[str] = None,
                            features: Dict[str, Any] = None) -> List[MemoryRecord]:
        research_domain = (features or {}).get("research_domain", "general")

        scored = []
        weights = self.rl_optimizer.get_current_weights()

        for source, memories in retrieved.items():
            if source == "user":
                user_mem = memories
                f = self._freshness(user_mem)
                score = self._SCORE_USER_BASE * f
                if user_mem.get("preferences", {}).get("response_style") == "concise":
                    score += self._SCORE_USER_PREF_BOOST * weights["explicit_feedback"]
                if f < self._FRESHNESS_ARCHIVE_THRESHOLD:
                    continue
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
                        importance=round(score * self._SCORE_USER_HABITS_MULT, 3), metadata=habits,
                    ))

            elif source == "knowledge":
                for mem in memories:
                    relevance = mem["relevance"]
                    recency = 1.0
                    if "last_updated" in mem["metadata"]:
                        age = (datetime.now(timezone.utc) - datetime.fromisoformat(mem["metadata"]["last_updated"])).days
                        recency = max(0, 1 - age / self._SCORE_RECENCY_DECAY_DAYS)
                    trust = mem["metadata"].get("trust_score", 0.5)
                    freshness = self._freshness(mem)
                    if freshness < self._FRESHNESS_ARCHIVE_THRESHOLD:
                        continue
                    # Domain boost: same-domain memories get +0.1
                    mem_domain = mem["metadata"].get("domain") or mem["metadata"].get("category", "")
                    domain_boost = self._SCORE_DOMAIN_BOOST if (research_domain != "general" and mem_domain == research_domain) else 0
                    score = (relevance * weights["relevance"] + recency * weights["recency"] + trust * weights["trust_score"] + domain_boost) * freshness
                    scored.append(MemoryRecord(source=source, content=mem["content"], importance=round(score, 3), metadata=mem))

            elif source == "experience":
                for mem in memories:
                    freshness = self._freshness(mem)
                    if freshness < self._FRESHNESS_ARCHIVE_THRESHOLD:
                        continue
                    recency_mult = self.cfg.get("retrieval", "recency_multiplier", 0.5)
                    score = (self._SCORE_EXPERIENCE_BASE * weights["relevance"] + mem["frequency"] * weights["frequency"] + recency_mult * weights["recency"]) * freshness
                    task_status = mem.get("metadata", {}).get("task_status", "")
                    if task_status == "failed": score *= self._SCORE_FAILED_MULT
                    elif task_status == "completed": score *= self._SCORE_COMPLETED_MULT
                    scored.append(MemoryRecord(source=source, content=mem["summary"], importance=round(score, 3), metadata=mem))

            elif source == "task_progress":
                scored.append(MemoryRecord(
                    source=source,
                    content=f"Task progress: {json.dumps(memories, ensure_ascii=False)}",
                    importance=self._SCORE_TASK_PROGRESS, metadata=memories,
                ))

            elif source == "task_history":
                for mem in memories:
                    freshness = self._freshness(mem)
                    if freshness < self._FRESHNESS_ARCHIVE_THRESHOLD:
                        continue
                    scored.append(MemoryRecord(
                        source=source,
                        content=f"Previous task: {mem['title']} ({mem['status']})",
                        importance=self._SCORE_TASK_HISTORY * (0.5 + 0.5 * freshness), metadata=mem,
                    ))

            elif source == "research":
                for mem in memories:
                    freshness = self._freshness(mem)
                    if freshness < self._FRESHNESS_ARCHIVE_THRESHOLD:
                        continue
                    mem_paper_domain = mem.get("domain", "")
                    research_domain_boost = self._SCORE_RESEARCH_DOMAIN_BOOST if (research_domain != "general" and mem_paper_domain == research_domain) else 0
                    score = (mem["relevance"] * weights["relevance"] + mem["importance_score"] * self._SCORE_RESEARCH_IMPORTANCE_WEIGHT + research_domain_boost) * freshness
                    key_points_str = "; ".join(mem.get("key_points", [])[:3])
                    scored.append(MemoryRecord(
                        source=source,
                        content=f"[{mem.get('domain','general')}] {mem['title']}: {key_points_str}",
                        importance=round(score, 3), metadata=mem,
                    ))

            elif source == "context":
                for ctx in memories:
                    freshness = self._freshness(ctx)
                    if freshness < self._FRESHNESS_ARCHIVE_THRESHOLD:
                        continue
                    messages = ctx.get("messages", [])
                    if not messages:
                        continue
                    ctx_platform = ctx.get("platform", "")
                    platform_mult = 1.0 if (not platform or ctx_platform == platform) else self._SCORE_CROSS_PLATFORM_MULT
                    scored.append(MemoryRecord(
                        source="context",
                        content=json.dumps(messages, ensure_ascii=False),
                        importance=round(self._SCORE_CONTEXT_BASE * platform_mult * (0.5 + 0.5 * freshness), 3),
                        metadata={
                            "session_id": ctx.get("session_id", ""),
                            "platform": ctx_platform,
                            "messages": messages,
                            "token_count": ctx.get("token_count", 0),
                        },
                    ))

        return scored

    def _freshness(self, record: Dict[str, Any]) -> float:
        """Compute Ebbinghaus forgetting curve freshness.

        freshness = 2^(-days_since_last_access / half_life)
        Tries: last_access_at → created_at → last_updated.
        Returns 1.0 if no date available.
        """
        date_str = (
            record.get("last_access_at") or
            record.get("metadata", {}).get("last_access_at", "") or
            record.get("created_at") or
            record.get("metadata", {}).get("created_at", "") or
            record.get("last_updated") or
            record.get("metadata", {}).get("last_updated", "")
        )
        if not date_str or date_str == "":
            return 1.0
        try:
            # Normalize naive datetime string (e.g. from SQLite) to aware UTC
            date_str = date_str.replace(" ", "T")
            if date_str.endswith("T"):
                date_str = date_str[:-1]
            if "+" not in date_str and not date_str.endswith("Z") and not date_str.endswith("+00:00"):
                date_str += "+00:00"
            days = (datetime.now(timezone.utc) - datetime.fromisoformat(date_str)).days
            if days < 0:
                return 1.0
            half_life = self.cfg.get("retrieval", "decay_half_life", default=self._DECAY_HALF_LIFE)
            return 2.0 ** (-days / max(half_life, 1))
        except (ValueError, TypeError):
            return 1.0

    def _update_last_access_for_retrieved(self, retrieved: Dict[str, Any], user_id: str):
        """Update last_access_at timestamps for records that were just retrieved."""
        if not self._persistence_enabled or not self.db._conn:
            return
        now = datetime.now(timezone.utc).isoformat()
        for source, records in retrieved.items():
            if source == "user":
                continue  # user memory has no row-level last_access_at
            if not isinstance(records, list):
                continue
            for rec in records:
                rec_id = rec.get("id") or rec.get("session_id") or ""
                if not rec_id:
                    continue
                table_map = {
                    "knowledge": "knowledge_memory",
                    "experience": "experience_memory",
                    "task_history": "task_memory",
                    "context": "context_memory",
                    "research": "research_papers",
                }
                table = table_map.get(source)
                if not table:
                    continue
                id_col = "id"
                if source == "context":
                    id_col = "session_id"
                try:
                    self.db._conn.execute(
                        f"UPDATE {table} SET last_access_at=? WHERE {id_col}=?",
                        (now, rec_id),
                    )
                except Exception:
                    pass
        try:
            self.db._conn.commit()
        except Exception:
            pass

    def search_transcripts(self, query: str, user_id: str = None,
                           project: str = None, limit: int = 5):
        if not self._persistence_enabled:
            return []
        return self.db.search_transcripts(query, user_id, project, limit)


    def store(self, user_id: str, task_id: str, context: List[Dict],
              task_status: str, success: bool = False, experience_summary: str = None,
              platform: str = None, title: str = None,
              project: str = "default", session_id: str = "",
              profile: str = "default", correction: bool = False) -> bool:
        """
        Store a task interaction and update all memory layers.
        """
        try:
            # Extract session title from first user message
            session_title = ""
            for msg in context:
                if msg.get("role") == "user" and not session_title:
                    content = msg.get("content", "")
                    session_title = f"{datetime.now(timezone.utc).strftime('%m%d-%H%M')}_{content[:120]}"
                self.context_agent.add_message(msg, session_id=session_id)
            # Note: add_message above is intentionally outside the DB transaction below.
            # In-memory context is the primary state; DB persistence is secondary.
            self.task_agent.create_task(user_id=user_id, task_id=task_id,
                                        title=title or session_title or "auto-task",
                                        steps=[{"step": "Initialize", "status": task_status}],
                                        profile=profile)
            task_tags = self._extract_task_tags(context) if hasattr(self, '_extract_task_tags') else []
            self._infer_user_preferences(context, user_id, platform=platform, profile=profile)
            self._infer_habits(user_id, context, profile=profile)

            # Extract task features（Shared by persistence and experience store）
            features = self._extract_task_features(
                " ".join(m.get("content","") for m in context if m.get("role")=="user"))
            self._update_user_history(user_id, project, platform, profile=profile)

            if self._persistence_enabled:
                lang = features.get("language", "en")
                user_data = self.user_agent.get(user_id, platform=platform, profile=profile)
                # Prepare experience data for the transaction
                exp_data = None
                if success or experience_summary:
                    steps_from_context = [m["content"] for m in context if m["role"] != "system"]
                    best_reply = ""
                    for msg in context:
                        if msg.get("role") == "assistant":
                            c = msg.get("content", "")
                            if len(c) > len(best_reply):
                                best_reply = c
                    exp_summary = experience_summary or best_reply[:200] or "System-generated experience summary"
                    exp_type = features.get("task_type", "general")
                    exp_data = {
                        "steps": steps_from_context,
                        "summary": exp_summary,
                        "task_type": exp_type,
                    }

                with self.db.transaction():
                    self.db.save_user(user_id,
                        preferences=user_data.get("preferences", {}),
                        habits=user_data.get("habits", {}),
                        history=user_data.get("history", []),
                        platform=platform,
                        profile=profile)
                    self.db.save_task(user_id, task_id, title or "auto-task", task_status,
                                      steps=[{"step": "Initialize", "status": task_status}],
                                      project=project, session_id=session_id or "",
                                      session_title=session_title, tags=task_tags,
                                      profile=profile, language=lang)
                    all_text = "".join(m.get("content", "") for m in context)
                    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', all_text))
                    token_est = int(chinese_chars * 1.5 + (len(all_text) - chinese_chars) / 4)
                    self.db.save_context(
                        session_id=f"{user_id}:{task_id}",
                        user_id=user_id,
                        messages=context,
                        token_count=token_est,
                        platform=platform or "default",
                        project=project,
                        profile=profile)
                    research_domain = features.get("research_domain", "general")
                    best_content = ""
                    for msg in context:
                        if msg.get("role") == "assistant":
                            c = msg.get("content", "")
                            if len(c) > len(best_content):
                                best_content = c
                    knowledge_content = best_content[:2000] if best_content else (experience_summary or "Auto-extracted knowledge")
                    if knowledge_content and knowledge_content != "Auto-extracted knowledge":
                        existing_kb = self.db.search_knowledge_by_content(knowledge_content)
                        if not existing_kb:
                            self.db.save_knowledge(
                                knowledge_id=f"{user_id}:{task_id}",
                                domain=research_domain,
                                content=knowledge_content,
                                metadata={"source": "task", "task_id": task_id, "user_id": user_id},
                                project=project,
                                session_id=session_id or "",
                                session_title=session_title, tags=task_tags,
                                profile=profile,
                                user_id=user_id,
                                language=lang)
                            self.knowledge_agent.add_document(knowledge_content, {
                                "source": "task", "task_id": task_id,
                                "user_id": user_id, "domain": research_domain,
                                "project": project, "session_id": session_id or "",
                                "session_title": session_title, "tags": task_tags,
                                "category": research_domain,
                            })
                    if exp_data:
                        self.db.save_experience(user_id, exp_data["task_type"], success,
                                     exp_data["steps"],
                                     exp_data["summary"],
                                     project=project,
                                     session_id=session_id or "",
                                     session_title=session_title, tags=task_tags,
                                     profile=profile, language=lang)

            # Store experience to in-memory agent (both persistence and non-persistence paths)
            if self._persistence_enabled:
                if exp_data:
                    self.experience_agent.store_experience(
                        task_id=task_id, success=success, steps=exp_data["steps"],
                        summary=exp_data["summary"],
                        user_id=user_id, task_type=exp_data["task_type"],
                        project=project, session_id=session_id or "",
                        session_title=session_title, tags=task_tags,
                        profile=profile,
                    )
            elif success or experience_summary:
                steps_from_context = [m["content"] for m in context if m["role"] != "system"]
                best_reply = ""
                for msg in context:
                    if msg.get("role") == "assistant":
                        c = msg.get("content", "")
                        if len(c) > len(best_reply):
                            best_reply = c
                exp_summary = experience_summary or best_reply[:200] or "System-generated experience summary"
                exp_type = features.get("task_type", "general")
                self.experience_agent.store_experience(
                    task_id=task_id, success=success, steps=steps_from_context,
                    summary=exp_summary,
                    user_id=user_id, task_type=exp_type,
                    project=project, session_id=session_id or "",
                    session_title=session_title, tags=task_tags,
                    profile=profile,
                )

            # O-3/O-4: Correction triggers immediate reflection; use adaptive batch otherwise
            if correction:
                logger.info("Correction detected — triggering immediate reflection")
                self._pending_reflection = True
                self._store_count.pop(user_id, None)
                if platform != "hermes":
                    self._trigger_auto_reflection(user_id)
            else:
                self._store_handle_reflection_trigger(user_id, platform)
            return True

        except Exception as e:
            logger.warning(f"store() failed: {e}")
            return False

    def get_recent_episodic(self, user_id: str, count: int = 8) -> List[Dict]:
        """Get recent N episodic records for ReflectiveAgent"""
        if self._persistence_enabled:
            return self.db.get_recent_episodic(user_id, count)
        return []

    def _store_handle_reflection_trigger(self, user_id: str, platform: str):
        """Extracted from store(): handle reflection scheduling with adaptive batch."""
        if not self._persistence_enabled:
            return
        with self._store_lock:
            self._store_count[user_id] = self._store_count.get(user_id, 0) + 1
            batch_size = self._get_adaptive_batch(user_id)
            if self._store_count[user_id] >= batch_size:
                del self._store_count[user_id]
                if platform == "hermes":
                    self._pending_reflection = True
                else:
                    self._trigger_auto_reflection(user_id)

    def _get_adaptive_batch(self, user_id: str) -> int:
        """Compute adaptive reflection batch size based on user activity.

        Low-frequency users (<10 sessions/week) → smaller batch (6) so they
        still trigger reflection. High-frequency users (50+) → larger batch
        (up to 20) to avoid excessive reflection calls.

        Formula: adaptive = clamp(7 * ln(sessions_last_7d + 1), 6, 20)
        """
        try:
            config_batch = self.reflective.config.get("batch_size", 8)
            # If config gives a single integer, use it directly (non-adaptive mode)
            if isinstance(config_batch, (int, float)) and not isinstance(config_batch, bool):
                return int(config_batch)
            if isinstance(config_batch, (list, tuple)):
                return int(random.uniform(config_batch[0], config_batch[1]))
        except Exception:
            pass
        # Adaptive calculation
        import math
        sessions = 0
        if self._persistence_enabled:
            try:
                sessions = self.db._get_recent_session_count(user_id, days=7)
            except (AttributeError, Exception):
                pass
        adaptive = int(max(6, min(20, 7 * math.log(max(sessions, 0) + 1))))
        return adaptive

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

    def _infer_user_preferences(self, context, user_id, platform=None, profile="default"):
        """Infer user preferences from conversation, adaptive to language.

        Supports 6 preference categories loaded from config:
        code_style, response_style, platform, language, depth, tone.
        """
        prefs = self.user_agent.get(user_id, profile=profile).get("preferences", {})
        infer_cfg = self.cfg.get_section("inference")
        min_occ = infer_cfg.get("min_occurrence", 2)

        all_content = " ".join(m.get("content", "") for m in context)
        lang = detect_language(all_content)
        inf_kw = get_inference_keywords(lang)
        default_infer = infer_cfg.get("keywords", {})

        # Define all 6 preference types with keyword sources
        pref_defs = {
            "response_style": {
                "concise": inf_kw.get("concise_response",
                    default_infer.get("concise_response", ["brief", "concise", "简短", "简洁"])),
                "detailed": inf_kw.get("detailed_type",
                    default_infer.get("detailed_type", ["type hint", "detailed", "Optional[str]"])),
            },
            "code_style": {
                "detailed": inf_kw.get("detailed_type",
                    default_infer.get("detailed_type", ["type hint", "Optional[str]"])),
                "concise": inf_kw.get("concise_code",
                    default_infer.get("concise_code", ["concise", "no comments", "简洁", "不要注释"])),
                "functional": inf_kw.get("functional_code",
                    default_infer.get("functional_code", ["lambda", "map", "filter", "comprehension"])),
            },
            "platform": {
                "python": inf_kw.get("platform_python",
                    default_infer.get("platform_python", ["python", "pip", "pandas", "numpy"])),
                "node": inf_kw.get("platform_node",
                    default_infer.get("platform_node", ["node", "npm", "yarn", "javascript", "typescript"])),
                "docker": inf_kw.get("platform_docker",
                    default_infer.get("platform_docker", ["docker", "dockerfile", "container"])),
            },
            "language": {
                "zh": inf_kw.get("lang_zh",
                    default_infer.get("lang_zh", ["python", "中文", "汉语"])),
                "en": inf_kw.get("lang_en",
                    default_infer.get("lang_en", ["python", "english"])),
            },
            "depth": {
                "beginner": inf_kw.get("depth_beginner",
                    default_infer.get("depth_beginner", ["beginner", "new to", "入门", "新手"])),
                "advanced": inf_kw.get("depth_advanced",
                    default_infer.get("depth_advanced", ["advanced", "expert", "深入", "高级", "profiling"])),
            },
            "tone": {
                "formal": inf_kw.get("tone_formal",
                    default_infer.get("tone_formal", ["formal", "official", "严谨", "规范"])),
                "casual": inf_kw.get("tone_casual",
                    default_infer.get("tone_casual", ["casual", "friendly", "随意", "简单"])),
            },
        }

        new_prefs = {}
        for pref_name, options in pref_defs.items():
            for value, keywords in options.items():
                if any(kw in all_content for kw in keywords):
                    count = sum(all_content.count(kw) for kw in keywords)
                    if count >= min_occ:
                        new_prefs[pref_name] = value
                        break

        if new_prefs:
            self.user_agent.update(user_id, "preferences", new_prefs, source="implicit", platform=platform, profile=profile)

    def _infer_habits(self, user_id, context, profile="default"):
        """Analyze conversation to build user habits."""
        all_content = " ".join(m.get("content", "") for m in context)
        habits = {}
        # Detect session time patterns
        hour = datetime.now(timezone.utc).hour
        if hour < 6:
            habits["active_time"] = "early_morning"
        elif hour < 12:
            habits["active_time"] = "morning"
        elif hour < 18:
            habits["active_time"] = "afternoon"
        else:
            habits["active_time"] = "evening"
        # Detect code language usage
        for kw, lang_name in [("python", "python"), ("javascript", "javascript"),
                              ("typescript", "typescript"), ("rust", "rust"),
                              ("golang", "go"), ("java", "java")]:
            if kw in all_content.lower():
                habits["frequent_language"] = lang_name
                break
        self.user_agent.update(user_id, "habits", habits, source="implicit", profile=profile)

    def _update_user_history(self, user_id, project, platform, profile="default"):
        """Record last project and platform in user history."""
        user = self.user_agent.get(user_id, profile=profile)
        history = user.get("history", [])
        entry = {"project": project, "platform": platform or "default",
                 "timestamp": datetime.now(timezone.utc).isoformat()}
        history.append(entry)
        max_history = self.cfg.get("user", "max_history_size", default=20)
        if len(history) > max_history:
            history = history[-max_history:]
        self.user_agent.update(user_id, "history", history, source="implicit", profile=profile)

    def record_feedback(self, user_id: str, task_id: str, feedback: str,
                        retrieved_memories: List[Dict], profile: str = "default"):
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
            self.db.save_rl_weights(user_id, self.rl_optimizer.ema_weights, profile=profile)
        logger.info(f"User {user_id} gave {feedback} feedback on task {task_id}")

    def sync_to_code_project(self, project_root: str, user_id: str,
                             profile: str = "default"):
        from pathlib import Path
        # Path traversal protection: resolve + verify it's within allowed scope
        root_path = Path(project_root).resolve()

        # Whitelist: home, cwd, and any extra paths from config
        home = Path.home().resolve()
        cwd = Path.cwd().resolve()
        allowed_bases = [home, cwd]
        extra_paths = self.cfg.get("sync", "allowed_paths", default=[])
        if isinstance(extra_paths, list):
            for p in extra_paths:
                try:
                    allowed_bases.append(Path(p).resolve())
                except Exception:
                    continue
        allowed = False
        for base in allowed_bases:
            try:
                root_path.relative_to(base)
                allowed = True
                break
            except ValueError:
                continue
        if not allowed:
            raise ValueError(f"Path outside allowed scope: {root_path}")

        try:
            echomind_dir = root_path / ".echomind"
            echomind_dir.mkdir(exist_ok=True)
        except PermissionError as e:
            raise ValueError(f"Cannot create directory at {root_path / '.echomind'}: {e}")

        user_mem = self.user_agent.get(user_id, profile=profile)
        exp_mem = self.experience_agent.find_similar_tasks(
            task_context=f"Code style preferences: {user_mem.get('preferences', {}).get('code_style', 'standard')}",
            task_type="code_review", min_success_rate=0.6,
            user_id=user_id, profile=profile,
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