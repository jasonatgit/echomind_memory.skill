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
    relevance: float = 0.5      # 检索时的相关性得分，供 RL 优化器使用
    trust_score: float = 0.5    # 记忆的可信度得分，供 RL 优化器使用


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
    _FRESHNESS_STALE_THRESHOLD = 0.3  # below this → stale state
    _FRESHNESS_ARCHIVE_THRESHOLD = 0.1  # below this → archived
    # Cognitive-position (nok/fok/exo) freshness thresholds. Independently
    # tunable from the lifecycle thresholds above so the two axes can drift
    # apart later, but default to the same values for now.
    _COGNITIVE_FOK_THRESHOLD = 0.3  # freshness below this → fok (fading)
    _COGNITIVE_EXO_THRESHOLD = 0.1  # freshness below this → exo (external)

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
            kpop_threshold=rl_config.get("kpop", {}).get("threshold", 2.0),
            kpop_max_extra=rl_config.get("kpop", {}).get("max_extra", 0.3),
        )
        self._persistence_enabled = False
        self._store_count: dict = {}
        self._pending_reflection_event = threading.Event()
        self._pending_reflection = False
        self._store_lock = threading.Lock()
        self._research_kw_cache = None
        # C-H1/P3: track the in-flight auto-reflection thread so shutdown can
        # join() it before closing the DB (a daemon thread left behind races
        # disable_persistence() and silently drops the reflection).
        self._reflection_thread = None

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
                # A1/P7 fix: restore the task's profile on reload. Without it,
                # a non-default-profile task would be born as "default" here,
                # silently breaking task-level profile isolation (research and
                # knowledge rows DO restore profile; tasks were the odd one out).
                profile=t.get("profile","default"),
                session_id=t.get("session_id",""),
                session_title=t.get("session_title",""),
                task_id=t.get("id", ""),
                title=t.get("title",""), status=t.get("status","pending"),
                steps=t.get("steps",[]), tags=t.get("tags",[]),
                created_at=self._parse_db_ts(t.get("created_at")),
                updated_at=self._parse_db_ts(t.get("updated_at")))
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
                summary=e.get("summary",""), tags=e.get("tags",[]),
                created_at=self._parse_db_ts(e.get("created_at")),
                last_access_at=self._parse_db_ts(e.get("last_access_at")))
            exp.frequency = e.get("frequency", 1)  # restore persisted frequency
            self.experience_agent.store[e.get("id","")] = exp
            exp.id = e.get("id", exp.id)  # align model id with DB key before indexing
            self.experience_agent._index_entry(exp)
            self.experience_agent._summary_index[int(hashlib.md5(f"{exp.user_id}:{exp.summary}".encode()).hexdigest(), 16) % (2**63 - 1)] = e.get("id","")
            loaded["experiences"] += 1

        # 4. Context memory（Restore with session isolation）
        # Load in reverse order (oldest first) so LRU eviction removes oldest, not newest
        for c in reversed(all_data.get("contexts", [])):
            session_id = c.get("session_id", "")
            messages = c.get("messages", [])
            for msg in messages:
                if isinstance(msg, dict) and "role" in msg:
                    self.context_agent.add_message(msg, session_id=session_id)
            loaded["contexts"] += 1

        # 5. Knowledge memory
        for k in all_data.get("knowledge", []):
            metadata = dict(k.get("metadata", {}))
            metadata.setdefault("project", k.get("project", "default"))
            # P8/A-M1 fix: carry the knowledge row's profile into in-memory
            # metadata so knowledge_agent.search's profile filter applies to
            # reloaded entries too (metadata.setdefault reads metadata first,
            # so any migration-era profile already stored wins).
            metadata.setdefault("profile", k.get("profile", "default"))
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
                user_id=k.get("user_id", k.get("metadata", {}).get("user_id", "default")),
                created_at=self._parse_db_ts(k.get("created_at")),
                last_access_at=k.get("last_access_at") or "")
            entry.id = k.get("id", entry.id)
            self.knowledge_agent.store[entry.id] = entry
            self.knowledge_agent._add_to_index(entry)
            self.knowledge_agent._content_index[
                int(hashlib.md5(entry.content.encode()).hexdigest(), 16) % (2**63 - 1)
            ] = entry.id
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
                importance_score=p.get("importance_score",0.5),
                created_at=self._parse_db_ts(p.get("created_at")),
                last_access_at=p.get("last_access_at") or "")
            self.research_agent.papers[paper.id] = paper
            loaded["papers"] += 1

        # 7. Research notes
        for n in all_data.get("research_notes", []):
            note = ResearchNote(id=n.get("id",""), user_id=n.get("user_id",""),
                project=n.get("project","default"),
                profile=n.get("profile","default"),
                topic=n.get("topic",""), content=n.get("content",""),
                linked_papers=n.get("linked_papers",[]),
                tags=n.get("tags",[]),
                created_at=self._parse_db_ts(n.get("created_at")),
                updated_at=self._parse_db_ts(n.get("updated_at")))
            self.research_agent.notes[note.id] = note
            loaded["notes"] += 1

        if sum(loaded.values()) > 0:
            logger.info(f"Loaded from DB: {loaded}")
        else:
            logger.info("Empty DB — fresh start")

        # 8. RL Weight restoration — use first user found (deterministic, not "last found")
        saved_weights = self.db.load_rl_weights("default")
        if not saved_weights and loaded.get("users", 0) > 0 and self.user_agent.store:
            for store_key, u in list(self.user_agent.store.items()):
                w = self.db.load_rl_weights(u.user_id, profile=u.profile)
                if w:
                    saved_weights = w
                    break  # Use first found, not last
        # If no user-specific weights found, try loading from user preferences JSON
        if not saved_weights and loaded.get("users", 0) > 0:
            for store_key, u in list(self.user_agent.store.items()):
                prefs = u.preferences if hasattr(u, 'preferences') else {}
                if isinstance(prefs, dict) and 'rl_weights' in prefs:
                    raw = prefs['rl_weights']
                    if isinstance(raw, str):
                        try:
                            import json
                            raw = json.loads(raw)
                        except (json.JSONDecodeError, TypeError):
                            raw = None
                    # A-M2/P16 fix: guard against a non-dict / corrupted value
                    # (e.g. a list from a bad merge). The eager indexing below
                    # (weights["relevance"], etc.) would otherwise crash
                    # retrieve_for_task. Only accept a dict of numbers.
                    if isinstance(raw, dict) and all(
                        isinstance(key, str) and isinstance(val, (int, float))
                        for key, val in raw.items()
                    ):
                        saved_weights = raw
                        logger.info("RL weights restored from preferences JSON for %s", u.user_id)
                    else:
                        logger.warning("RL weights in preferences JSON for %s are invalid (type=%s); ignoring",
                                       u.user_id, type(raw).__name__)
                    break
        if saved_weights:
            # Route through load_weights_for_user so missing/partial dimensions
            # are schema-completed (B-M1/P9) instead of crashing later in
            # _compute_importance's eager weights["..."] indexing.
            self.rl_optimizer.load_weights_for_user(saved_weights)
            logger.info(f"RL weights restored: {self.rl_optimizer.get_current_weights()}")

        # P1-1: Initialize memory states for loaded records
        self._update_memory_states()

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

    def _trigger_auto_reflection(self, user_id: str, profile: str = None,
                                 platform: str = "http",
                                 batch_size: int = None):
        """Schedule auto-reflection in background thread (non-blocking).

        C-M1/P14: accepts profile and platform so the Hermes path can scope the
        episodic records to the active profile and attribute the reflection to
        "hermes" instead of the hardcoded "http". Non-Hermes callers keep the
        original "http" behavior.

        M2/P11: accepts the already-drawn batch_size from the trigger path.
        Previously _run re-drew random.uniform(config_range) on its own, so a
        small second draw could fall under min_records and deterministically
        drop a reflection that the trigger had already decided to fire.
        """
        import threading
        agent = self

        def _run():
            try:
                batch_size = batch_size if batch_size is not None else agent.reflective.config.get("batch_size", 8)
                if isinstance(batch_size, (list, tuple)):
                    batch_size = int(random.uniform(batch_size[0], batch_size[1]))
                records = agent.get_recent_episodic(user_id, count=batch_size,
                                                    profile=profile)
                min_records = agent.reflective.config.get("min_records", 6)
                if len(records) < min_records:
                    return
                from .llm_client import get_llm_client
                llm = get_llm_client()
                if llm and llm.available:
                    result = agent.reflective.reflect_with_llm(
                        records, user_id, platform, llm.chat)
                    if result:
                        logger.info(
                            "Auto-reflection: %d insights (confidence=%.2f)",
                            len(result.key_insights), result.confidence)
                        meta = {"source": "auto_reflection",
                                "record_count": len(records)}
                        if profile:
                            meta["profile"] = profile
                        if agent._persistence_enabled:
                            agent.db.save_reflection({
                                "id": f"auto:{user_id}:{int(datetime.now(timezone.utc).timestamp())}",
                                "user_id": user_id,
                                "platform": platform,
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
                                "meta": meta,
                            })
                        else:
                            logger.warning(
                                "Auto-reflection result dropped because persistence was "
                                "disabled before the background thread ran (user=%s).",
                                user_id)
            except Exception as e:
                logger.debug("Auto-reflection skipped: %s", e)

        t = threading.Thread(target=_run, daemon=True)
        self._reflection_thread = t
        t.start()

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
        # L-5 fix: match domain IDs exactly (normalize punctuation/whitespace)
        # instead of a raw substring scan. Substring matching mis-triggers when
        # an ID is a prefix of another (e.g. "ai" matching "ai_ethics" output)
        # or when a keyword inside the text happens to contain an ID literally.
        # Longest IDs first so a prefix relationship can't shadow the real one.
        cleaned = "".join(ch for ch in result if ch.isalnum() or ch == "_")
        for did in sorted(domain_keywords, key=len, reverse=True):
            if cleaned == did:
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
                tp = self.task_agent.get_task_progress(composite_id)
                # L-1 fix: carry task_id/user_id so the freshness updater can
                # refresh task_memory.last_access_at (get_task_progress alone
                # does not expose them, so the row never refreshed).
                if tp:
                    tp["task_id"] = task_id
                    tp["user_id"] = user_id
                retrieved["task_progress"] = tp
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

        # Load per-user RL weights for isolated scoring
        if self._persistence_enabled:
            user_weights = self.db.load_rl_weights(user_id, profile=profile)
            self.rl_optimizer.load_weights_for_user(user_weights)

        scored = self._compute_importance(retrieved, task_context, user_id, platform, features)
        # P0-2: Group-by-domain sampling — ensure knowledge diversity in top-8
        ranked = sorted(scored, key=lambda x: x.importance, reverse=True)
        top_memories = self._diversify_top_k(ranked, top_k=8)
        confidence = (sum(m.importance for m in top_memories)
                      / max(len(top_memories), 1))

        # Update last_access_at for retrieved records so freshness reflects true access time
        if self._persistence_enabled:
            self._update_last_access_for_retrieved(retrieved, user_id)

        # P1-4: behavior_hints — expose RL state and user preferences as structured hints
        user_prefs = retrieved.get("user", {})
        prefs = user_prefs.get("preferences", {}) if isinstance(user_prefs, dict) else {}
        cw = self.rl_optimizer.get_current_weights()
        behavior_hints = {
            "preferred_response_style": prefs.get("response_style", ""),
            "preferred_code_style": prefs.get("code_style", ""),
            "content_language": prefs.get("language", ""),
            "preferred_depth": prefs.get("depth", ""),
            "preferred_tone": prefs.get("tone", ""),
            "success_rate_estimate": round(self._estimate_success_rate(), 3),
            "rl_state": {
                "relevance_weight": round(cw.get("relevance", 0.5), 3),
                "recency_weight": round(cw.get("recency", 0.5), 3),
                "frequency_weight": round(cw.get("frequency", 0.5), 3),
                "explicit_feedback_weight": round(cw.get("explicit_feedback", 0.5), 3),
                "trust_weight": round(cw.get("trust_score", 0.5), 3),
            },
            "rl_weights": {k: round(v, 3) for k, v in cw.items()},
            "hot_domains": self._get_hot_domains(threshold=3),
        }

        self._update_memory_states(user_id)

        return {
            "working_memory": top_memories,
            "behavior_hints": behavior_hints,
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
                    trust_score=0.6,
                ))
                habits = user_mem.get("habits", {})
                if habits:
                    scored.append(MemoryRecord(
                        source=source,
                        content=f"User habits: {json.dumps(habits, ensure_ascii=False)}",
                        importance=round(score * self._SCORE_USER_HABITS_MULT, 3), metadata=habits,
                        trust_score=0.5,
                    ))

            elif source == "knowledge":
                for mem in memories:
                    relevance = mem["relevance"]
                    freshness = self._freshness(mem)  # unified Ebbinghaus freshness (safe tz handling)
                    if freshness < self._FRESHNESS_ARCHIVE_THRESHOLD:
                        continue
                    trust = mem["metadata"].get("trust_score", 0.5)
                    # Domain boost: same-domain memories get +0.1
                    mem_domain = mem["metadata"].get("domain") or mem["metadata"].get("category", "")
                    domain_boost = self._SCORE_DOMAIN_BOOST if (research_domain != "general" and mem_domain == research_domain) else 0
                    score = (relevance * weights["relevance"] + freshness * weights["recency"] + trust * weights["trust_score"] + domain_boost) * freshness
                    scored.append(MemoryRecord(source=source, content=mem["content"], importance=round(score, 3), metadata=mem, relevance=relevance, trust_score=trust))

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
                    trust = mem.get("metadata", {}).get("trust_score", 0.5) if isinstance(mem.get("metadata"), dict) else 0.5
                    scored.append(MemoryRecord(source=source, content=mem["summary"], importance=round(score, 3), metadata=mem,
                                               relevance=mem.get("relevance", 0.5), trust_score=trust))

            elif source == "task_progress":
                scored.append(MemoryRecord(
                    source=source,
                    content=f"Task progress: {json.dumps(memories, ensure_ascii=False)}",
                    importance=self._SCORE_TASK_PROGRESS, metadata=memories,
                    relevance=0.7, trust_score=0.6,
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
                        relevance=0.4, trust_score=0.5,
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
                        relevance=mem.get("relevance", 0.5), trust_score=0.6,
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
                        relevance=0.3, trust_score=0.4,
                    ))

        if self.cfg.get_section("rl").get("gspo", {}).get("enabled", True):
            scored = self._gspo_cluster(scored)
        return scored

    def _gspo_cluster(self, scored: List[MemoryRecord]) -> List[MemoryRecord]:
        """GSPO-style cluster aggregation: same-source same-session memories
        share a geometric-mean importance score.

        Geometric mean = exp(mean(log(importance))) — more robust to outliers
        than arithmetic mean. Only active for clusters of size >= 2 where
        within-cluster variance exceeds threshold.
        """
        import math
        clusters = {}
        for mem in scored:
            sid = ""
            if isinstance(mem.metadata, dict):
                sid = mem.metadata.get("session_id", "") or mem.metadata.get("metadata", {}).get("session_id", "")
            key = f"{mem.source}:{sid}"
            clusters.setdefault(key, []).append(mem)
        for key, members in clusters.items():
            if len(members) < 2:
                continue
            imps = [max(m.importance, 1e-8) for m in members]
            mean_imp = sum(imps) / len(imps)
            variance = sum((x - mean_imp) ** 2 for x in imps) / len(imps)
            cv = math.sqrt(variance) / max(mean_imp, 1e-8)
            if cv < 0.15:
                continue
            log_mean = sum(math.log(x) for x in imps) / len(imps)
            geo = math.exp(log_mean)
            for m in members:
                m.importance = geo
        return scored

    def _diversify_top_k(self, ranked: List[MemoryRecord], top_k: int = 8) -> List[MemoryRecord]:
        """Diversify top-K by domain grouping.

        Ensures at least one item from each domain that appears in the
        top (top_k × 2) candidates makes it into the final top_k.
        Falls back to straight ranking when grouping is not beneficial.
        """
        if not ranked:
            return []
        # Extract domain from metadata for knowledge/experience sources
        def _item_domain(mem: MemoryRecord) -> str:
            if isinstance(mem.metadata, dict):
                # Direct domain key (experience, research, context)
                d = mem.metadata.get("domain", "") or mem.metadata.get("category", "") or ""
                if d:
                    return d
                # Nested: knowledge_agent.search() puts whole result dict as metadata,
                # with domain/category inside mem.metadata["metadata"]
                inner = mem.metadata.get("metadata", {})
                if isinstance(inner, dict):
                    return inner.get("domain", "") or inner.get("category", "") or ""
            return ""
        # Items with empty domain keep their rank position
        domains_seen: set[str] = set()
        result: List[MemoryRecord] = []
        for mem in ranked:
            if len(result) >= top_k:
                break
            domain = _item_domain(mem)
            if not domain or domain == "general":
                # items without domain always pass through
                result.append(mem)
            elif domain not in domains_seen:
                # First item of this domain — guaranteed spot
                domains_seen.add(domain)
                result.append(mem)
            else:
                # Already have a representative from this domain in result
                # only include if we have room AND this item's importance
                # is within 80% of the last included
                if len(result) < top_k:
                    last_imp = result[-1].importance
                    if mem.importance >= last_imp * 0.8:
                        result.append(mem)
        return result[:top_k]

    @staticmethod
    def _parse_db_ts(value) -> Optional[datetime]:
        """Parse a DB timestamp value (string or datetime) into an aware UTC datetime.

        Handles both naive SQLite format ('YYYY-MM-DD HH:MM:SS') and aware ISO format.
        Returns None when value is empty/invalid so callers can fall back to defaults.
        """
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value
        if isinstance(value, str) and value.strip():
            s = value.strip().replace(" ", "T")
            if "+" not in s and not s.endswith("Z") and not s.endswith("+00:00"):
                s += "+00:00"
            try:
                return datetime.fromisoformat(s)
            except ValueError:
                return None
        return None

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
            record.get("metadata", {}).get("last_updated", "") or
            record.get("updated_at") or
            record.get("metadata", {}).get("updated_at", "") or
            ""
        )
        if not date_str or date_str == "":
            return 1.0
        dt = self._parse_db_ts(date_str)
        if dt is None:
            return 1.0
        days = (datetime.now(timezone.utc) - dt).days
        if days < 0:
            return 1.0
        half_life = self.cfg.get("retrieval", "decay_half_life", default=self._DECAY_HALF_LIFE)
        return 2.0 ** (-days / max(half_life, 1))

    def _update_memory_states(self, user_id: str = ""):
        """Scan recent memories and update states based on Ebbinghaus freshness.

        Maps freshness scores to states:
          freshness 0.1-0.3 → stale
          freshness < 0.1  → archived
        Transitions: active→stale, active/stale→archived.

        Knowledge entries additionally migrate cognitive_pos (nok/fok/exo) in
        lockstep with the freshness decay, using independent thresholds so the
        cognitive-position axis can be tuned separately from lifecycle state.
        """
        if not self._persistence_enabled or not self.db._conn:
            return
        try:
            limit = self.cfg.get("retrieval", "state_scan_limit", default=1000)
        except Exception:
            limit = 1000
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 1000
        try:
            for mem_type, table, id_col in [
                ("knowledge", "knowledge_memory", "id"),
                ("experience", "experience_memory", "id"),
                ("task", "task_memory", "id"),
                ("context", "context_memory", "session_id"),
            ]:
                with self.db._lock:
                    rows = self.db._conn.execute(
                        f"SELECT {id_col} as rid, created_at, last_access_at, last_updated "
                        f"FROM {table} ORDER BY created_at DESC LIMIT ?",
                        (limit,),
                    ).fetchall()
                for r in rows:
                    current = self.db.get_memory_state(mem_type, r["rid"])
                    if current in ("archived", "superseded"):
                        continue
                    freshness = self._freshness(dict(r))
                    if freshness < self._FRESHNESS_ARCHIVE_THRESHOLD:
                        if current in ("active", "stale"):
                            self.db.save_memory_state(mem_type, r["rid"], "archived",
                                                       "freshness_decay", source="system")
                    elif freshness < self._FRESHNESS_STALE_THRESHOLD and current == "active":
                        self.db.save_memory_state(mem_type, r["rid"], "stale",
                                                  "freshness_decay", source="system")
                    # cognitive_pos lifecycle (knowledge only)
                    if mem_type == "knowledge":
                        self._migrate_cognitive_pos(r["rid"], freshness)
        except Exception as e:
            logger.debug("Memory state update skipped: %s", e)

    def _migrate_cognitive_pos(self, knowledge_id: str, freshness: float):
        """Migrate a knowledge entry's cognitive_pos by freshness.

        nok (current context) → fok (fading) → exo (external deep memory).
        Persists to both the DB metadata JSON and the in-memory agent so the
        markdown archive reflects the migration without a reload.
        """
        if freshness < self._COGNITIVE_EXO_THRESHOLD:
            new_pos = "exo"
        elif freshness < self._COGNITIVE_FOK_THRESHOLD:
            new_pos = "fok"
        else:
            new_pos = "nok"
        try:
            with self.db._lock:
                self.db._conn.execute(
                    "UPDATE knowledge_memory SET metadata = json_set("
                    "CASE WHEN json_type(metadata) IS NULL THEN '{}' ELSE metadata END, "
                    "'$.cognitive_pos', ?) WHERE id = ?",
                    (new_pos, knowledge_id),
                )
            self.db._maybe_commit()
        except Exception as e:
            logger.debug("cognitive_pos DB migration failed: %s", e)
        entry = self.knowledge_agent.store.get(knowledge_id)
        if entry is not None:
            entry.metadata["cognitive_pos"] = new_pos

    def _update_last_access_for_retrieved(self, retrieved: Dict[str, Any], user_id: str):
        """Update last_access_at timestamps for records that were just retrieved."""
        if not self._persistence_enabled or not self.db._conn:
            return
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")  # match DB datetime('now') format
        for source, records in retrieved.items():
            if source == "user":
                continue  # user memory has no row-level last_access_at
            if source == "task_progress":
                # L-1 fix: task_progress is a single dict (not a list)
                if isinstance(records, dict) and records:
                    records = [records]
                else:
                    continue
            if not isinstance(records, list):
                continue
            for rec in records:
                rec_id = rec.get("id") or rec.get("session_id") or rec.get("task_id") or ""
                if not rec_id:
                    continue
                table_map = {
                    "knowledge": "knowledge_memory",
                    "experience": "experience_memory",
                    "task_progress": "task_memory",
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
                elif source in ("task_history", "task_progress") and rec.get("task_id"):
                    # task_memory rows are keyed by composite user:task_id
                    # (L-1: task_progress added so its last_access_at refreshes)
                    rec_id = f"{rec.get('user_id') or user_id}:{rec.get('task_id')}"
                try:
                    with self.db._lock:
                        self.db._conn.execute(
                            f"UPDATE {table} SET last_access_at=? WHERE {id_col}=?",
                            (now, rec_id),
                        )
                    # L-4 fix: keep the in-RAM ResearchPaper model in sync with the
                    # DB so paper freshness decays on subsequent searches (the RAM
                    # dict is the actual data source for search_papers).
                    if source == "research" and rec_id in self.research_agent.papers:
                        self.research_agent.papers[rec_id].last_access_at = now
                except Exception:
                    pass
        try:
            with self.db._lock:
                self.db._conn.commit()
        except Exception:
            pass

    def search_transcripts(self, query: str, user_id: str = None,
                           project: str = None, limit: int = 5):
        if not self._persistence_enabled:
            return []
        return self.db.search_transcripts(query, user_id, project, limit)

    @staticmethod
    def _resolve_epistemic(source: str) -> str:
        """Resolve the epistemic mode (Moltspeak sav-verbs) for a new knowledge entry.

        Returns one of: 'user_provided' | 'reasoned' | 'fuzzy' | 'referenced' | 'unknown'.
        Zero LLM cost — purely heuristic based on source type at write time.

        W-1: dropped the unused `content` parameter; callers now pass the real
        source so different provenance isn't collapsed to a hardcoded 'assistant'.
        """
        if source == "user_direct":
            return "user_provided"
        if source == "reflection":
            return "reasoned"
        if source == "assistant":
            return "fuzzy"
        if source == "external_import":
            return "referenced"
        return "unknown"

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
            # Extract task features before create_task to get task_type
            features = self._extract_task_features(
                " ".join(m.get("content","") for m in context if m.get("role")=="user"))
            self.task_agent.create_task(user_id=user_id, task_id=task_id,
                                        title=title or session_title or "auto-task",
                                        steps=[{"step": "Initialize", "status": task_status}],
                                        profile=profile, project=project,
                                        task_type=features.get("task_type"))
            task_tags = self._extract_task_tags(context)
            self._infer_user_preferences(context, user_id, platform=platform, profile=profile)
            self._infer_habits(user_id, context, profile=profile)

            # Extract task features (Shared by persistence and experience store)
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
                        # P3-2: Extract entities from content before persisting
                        kb_metadata = {"source": "task", "task_id": task_id, "user_id": user_id}
                        entities = self._extract_entities(best_content or experience_summary or "")
                        if entities:
                            kb_metadata["entities"] = entities
                        # W-1 fix: resolve epistemic mode from the real source instead of a hardcoded
                        # "assistant" (which collapsed every entry to fuzzy). Knowledge
                        # distilled by the assistant LLM → fuzzy; knowledge taken from a
                        # user-provided experience summary → user_provided.
                        if best_content:
                            kb_metadata["epistemic_mode"] = self._resolve_epistemic("assistant")
                            kb_metadata["epistemic_detail"] = "generated by LLM, unverified"
                        else:
                            kb_metadata["epistemic_mode"] = self._resolve_epistemic("user_direct")
                            kb_metadata["epistemic_detail"] = "derived from user-provided experience summary"
                        # Moltspeak nok~: newly-created knowledge lives in the current context (high fidelity)
                        kb_metadata["cognitive_pos"] = "nok"
                        if not existing_kb:
                            self.db.save_knowledge(
                                knowledge_id=f"{user_id}:{task_id}",
                                domain=research_domain,
                                content=knowledge_content,
                                metadata=kb_metadata,
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
                                # P8/A-M1 fix: tag in-memory knowledge with its profile
                                # so knowledge_agent.search's profile filter isn't a
                                # silent no-op until a reload. This mirrors the DB row,
                                # closing the cross-profile in-memory leak.
                                "profile": profile,
                            }, entry_id=f"{user_id}:{task_id}")
                    if exp_data:
                        # Deterministic id from summary hash — matches experience_agent._summary_index,
                        # so DB ON CONFLICT dedups consistently with in-memory (fixes reload duplication)
                        exp_hash = int(hashlib.md5(f"{user_id}:{exp_data['summary']}".encode()).hexdigest(), 16)
                        exp_id = f"exp:{user_id}:{exp_hash % (2**63-1)}"
                        self.db.save_experience(user_id, exp_data["task_type"], success,
                                     exp_data["steps"],
                                     exp_data["summary"],
                                     project=project,
                                     session_id=session_id or "",
                                     session_title=session_title, tags=task_tags,
profile=profile, language=lang, experience_id=exp_id)

                # P1-1: Initialize memory states for newly created records
                if self._persistence_enabled:
                    current_w = self.rl_optimizer.get_current_weights()
                    weight_reason = json.dumps({"weights": current_w})
                    task_pk = f"{user_id}:{task_id}"
                    self.db.save_memory_state("user", user_id, "active", reason=weight_reason, source="store")
                    self.db.save_memory_state("task", task_pk, "active", reason=weight_reason, source="store")
                    self.db.save_memory_state("context", task_pk, "active", reason=weight_reason, source="store")
                    if exp_data:
                        self.db.save_memory_state("experience", exp_id, "active", reason=weight_reason, source="store")
                    if knowledge_content and knowledge_content != "Auto-extracted knowledge":
                        self.db.save_memory_state("knowledge", task_pk, "active", reason=weight_reason, source="store")

                # P2-1: Evolution detection — scan existing knowledge via Jaccard, classify relations
                if knowledge_content and knowledge_content != "Auto-extracted knowledge":
                    self._detect_knowledge_evolution(knowledge_content, user_id, research_domain,
                                                     knowledge_id=task_pk,
                                                     origin_agent=platform or "default",
                                                     origin_session_id=session_id or "")

            # Store experience to in-memory agent (both persistence and non-persistence paths)
            if self._persistence_enabled:
                if exp_data:
                    self.experience_agent.store_experience(
                        task_id=task_id, success=success, steps=exp_data["steps"],
                        summary=exp_data["summary"],
                        user_id=user_id, task_type=exp_data["task_type"],
                        project=project, session_id=session_id or "",
                        session_title=session_title, tags=task_tags,
                        profile=profile, entry_id=exp_id,
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
                with self._store_lock:
                    self._store_count.pop(user_id, None)
                if platform != "hermes":
                    self._trigger_auto_reflection(user_id)
            else:
                self._store_handle_reflection_trigger(user_id, platform)
            self._update_memory_states(user_id)
            return True

        except Exception as e:
            logger.error("store() failed", exc_info=True)
            return False

    def get_recent_episodic(self, user_id: str, count: int = 8,
                            profile: str = None) -> List[Dict]:
        """Get recent N episodic records for ReflectiveAgent"""
        if self._persistence_enabled:
            return self.db.get_recent_episodic(user_id, count, profile=profile)
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
                    # M2/P11: pass the DRAWN batch_size so _trigger_auto_reflection
                    # does not re-draw and possibly under-fetch below min_records.
                    self._trigger_auto_reflection(user_id, batch_size=batch_size)

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
        # L-3 fix: match case-insensitively (English keywords like "Concise" /
        # "Python" would otherwise be missed). Chinese keywords are unaffected.
        all_content_lower = all_content.lower()
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
                    default_infer.get("lang_zh", ["中文", "汉语"])),
                "en": inf_kw.get("lang_en",
                    default_infer.get("lang_en", ["english", "english please"])),
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
                lkws = [k.lower() for k in keywords]
                if any(kw in all_content_lower for kw in lkws):
                    count = sum(all_content_lower.count(lkw) for lkw in lkws)
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
        self.user_agent.replace_history(user_id, history, profile=profile)

    def _estimate_success_rate(self, window: int = 50) -> float:
        """Estimate recent success rate from RL history.

        Maps avg_reward (range -1..+1) to 0..1 success rate.
        Returns 0.5 neutral when no history available.
        """
        history = self.rl_optimizer.history[-window:]
        if not history:
            return 0.5
        return sum(0.5 + h["avg_reward"] / 2 for h in history) / len(history)

    def record_feedback(self, user_id: str, task_id: str, feedback: str,
                        retrieved_memories: List, profile: str = "default"):
        if feedback not in ["positive", "negative"]:
            raise ValueError("feedback must be 'positive' or 'negative'")
        # Defensive: convert Pydantic MemoryRecord objects to dicts
        # (in case caller passes retrieve_for_task return directly without JSON round-trip)
        _normalized_memories = [
            m.model_dump() if hasattr(m, 'model_dump') else m
            for m in (retrieved_memories or [])
        ]
        from .learning.rl_weight_optimizer import FeedbackRecord
        # H-1 fix: reload this user's own weights before updating. The shared
        # singleton optimizer may currently hold a different user's weights
        # (from their most-recent retrieve); without this, add_feedback would
        # update and persist the wrong user's weights.
        if self._persistence_enabled:
            user_weights = self.db.load_rl_weights(user_id, profile=profile)
            self.rl_optimizer.load_weights_for_user(user_weights)
        cw = self.rl_optimizer.get_current_weights()
        feedback_record = FeedbackRecord(
            user_id=user_id, task_id=task_id,
            retrieved_memories=_normalized_memories, user_feedback=feedback,
            metadata={"weights_snapshot": cw, "feedback": feedback},
        )
        self.rl_optimizer.add_feedback(feedback_record)
        # Persist RL weights (now guaranteed to be this user's weights)
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

        summary = "=== EchoMind Memory Health ===\n\n"

        # P1-2: Briefing section — active topics, health stats
        try:
            stats = self.db.get_memory_stats()
            summary += "## Memory Health\n\n"
            summary += "| Type | Active | Stale | Archived | Growth 7d |\n"
            summary += "|------|--------|-------|----------|----------|\n"
            for mem_type in ("knowledge", "experience", "task", "context"):
                s = stats.get(mem_type, {})
                growth = stats.get(f"{mem_type}_7d_growth", 0)
                summary += f"| {mem_type} | {s.get('active',0)} | {s.get('stale',0)} | {s.get('archived',0)} | +{growth} |\n"
            summary += f"\nDecay: half_life={self._DECAY_HALF_LIFE}d, stale<0.3, archive<0.1\n"
            summary += "\n### Flags\n"
            flags = self._get_flags(user_id)
            if flags:
                for f in flags[:5]:
                    summary += f"- [{f['type']}] {f.get('memory_id','')}: {f.get('content','')[:100]}\n"
            else:
                summary += "No issues found.\n"
        except Exception:
            summary += "(Health report unavailable)\n"

        summary += "\n=== EchoMind Memory summary ===\n"
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

        # P0-3: Export human-readable profile.md — inspired by Raven's user.md format
        try:
            profile_lines = ["# EchoMind Memory Profile\n"]
            # User preferences section
            prefs = user_mem.get("preferences", {})
            if prefs:
                profile_lines.append("## Preferences\n")
                for k, v in sorted(prefs.items()):
                    if isinstance(v, (str, int, float, bool)):
                        profile_lines.append(f"- **{k}**: {v}\n")
                profile_lines.append("\n")
            # Knowledge summary
            all_kb = self.knowledge_agent.search_all(user_id=user_id, profile=profile)
            if all_kb:
                profile_lines.append(f"## Knowledge ({len(all_kb)} entries)\n")
                for kb in all_kb[:15]:
                    profile_lines.append(f"- {kb.get('content', '')[:120]}\n")
                profile_lines.append("\n")
            # Experience summary
            if exp_mem:
                profile_lines.append(f"## Recent Experience ({len(exp_mem)} entries)\n")
                for exp in exp_mem[:5]:
                    status = "✅" if exp.get("success") else "❌"
                    profile_lines.append(f"- {status} {exp.get('summary', '')[:100]}\n")
                profile_lines.append("\n")
            # Research papers
            papers = list(self.research_agent.papers.values())
            if papers:
                profile_lines.append(f"## Research Papers ({len(papers)} entries)\n")
                for p in papers[:5]:
                    profile_lines.append(f"- **{p.title}** ({p.domain})\n")
                profile_lines.append("\n")
            # Hot domains
            hot = self._get_hot_domains(threshold=3)
            if hot:
                profile_lines.append("## Active Topics\n")
                for d in hot:
                    profile_lines.append(f"- {d}\n")
                profile_lines.append("\n")
            profile_lines.append(f"---\n*Generated: {datetime.now(timezone.utc).isoformat()}*\n")
            (echomind_dir / "profile.md").write_text(
                "".join(profile_lines), encoding="utf-8")
        except Exception:
            logger.warning("Failed to export profile.md")
        # Export full markdown memory archive (v1.2.9)
        try:
            memory_md = self.export_memory_to_markdown(user_id, profile)
            (echomind_dir / "memory.md").write_text(memory_md, encoding="utf-8")
        except Exception:
            logger.warning("Failed to export memory.md")
        logger.info(f"Synced EchoMind memories to {echomind_dir}")

    def get_context(self) -> List[Dict]:
        return self.context_agent.get_context()

    def clear_context(self):
        self.context_agent.clear()

    # ── P2-1: Knowledge evolution ──────────────────────

    @staticmethod
    def _jaccard_similarity(text1: str, text2: str) -> float:
        """Jaccard similarity on tokens — fast, zero-LLM approx.

        P8 fix: the previous `text.lower().split()` was whitespace-based, so
        for CJK text (no spaces) it produced a single giant token per string
        and Jaccard≈0 — silently disabling knowledge-evolution detection for
        Chinese. Now tokenize via lang_utils (which handles EN words and ZH
        char n-grams) and, for CJK, additionally union in character bigrams
        so short overlapping phrases still score non-zero.
        """
        if not text1 or not text2:
            return 0.0
        from .lang_utils import tokenize as _tok, detect_language as _det

        def _tokens(t: str) -> set:
            lang = _det(t)
            toks = set(_tok(t, lang)) if t.strip() else set()
            if lang == "zh":
                import re as _re
                segs = _re.findall(r"[\u4e00-\u9fff]+", t.lower())
                big = {s[i:i+2] for s in segs for i in range(len(s) - 1) if len(s) >= 2}
                toks |= big
            return toks

        set1 = _tokens(text1)
        set2 = _tokens(text2)
        inter = len(set1 & set2)
        union = len(set1 | set2)
        return inter / union if union > 0 else 0.0

    def _classify_relation(self, sim: float) -> Optional[str]:
        """Classify relation type from Jaccard similarity alone."""
        if sim >= 0.9:
            return "replaces"
        if sim >= 0.7:
            return "enriches"
        return None

    def _llm_classify_relation(self, source_text: str, target_text: str, sim: float) -> Optional[str]:
        """Use LLM to precisely classify relation (replaces/enriches/confirms/challenges)."""
        try:
            llm = self._get_llm_client() if hasattr(self, '_get_llm_client') else None
            if not llm or not llm.available:
                return self._classify_relation(sim)
            prompt = (
                "Compare these two knowledge statements. Reply with ONE word:\n"
                "- 'replaces' if statement B makes statement A obsolete\n"
                "- 'enriches' if B adds useful detail to A\n"
                "- 'confirms' if B independently validates A\n"
                "- 'challenges' if B contradicts A\n"
                "- 'none' if unrelated\n\n"
                f"A: {source_text[:300]}\n\nB: {target_text[:300]}\n\n"
                "Relation:"
            )
            result = llm.chat(prompt, temperature=0, max_tokens=10).strip().lower()
            valid = {"replaces", "enriches", "confirms", "challenges"}
            return result if result in valid else self._classify_relation(sim)
        except Exception:
            return self._classify_relation(sim)

    # ── P0-1: Hot tag statistics — domain-level knowledge count for tag-driven reflection ──

    def _get_hot_domains(self, threshold: int = 3) -> List[str]:
        """Return knowledge domains whose entry count >= threshold.

        Used to trigger domain-specific lightweight reflection
        (inspired by Raven's hot_tags -> refresh_section pattern).
        """
        if not self._persistence_enabled or not self.knowledge_agent:
            return []
        counts: Dict[str, int] = {}
        for entry in self.knowledge_agent.store.values():
            domain = entry.metadata.get("domain", "") or entry.metadata.get("category", "")
            if domain and domain != "general":
                counts[domain] = counts.get(domain, 0) + 1
            tags = entry.metadata.get("tags", [])
            if isinstance(tags, list):
                for tag in tags:
                  if isinstance(tag, str):
                    key = f"_tag:{tag}"
                    counts[key] = counts.get(key, 0) + 1
        hot = [d for d, c in counts.items() if c >= threshold]
        hot.sort(key=lambda d: counts.get(d, 0), reverse=True)
        return hot[:10]

    # ── P2-2: Flags ────────────────────────────────────

    def _get_flags(self, user_id: str) -> List[Dict]:
        """Scan for needs_verify and contradiction flags (stale handled by P1-1 state machine)."""
        flags = []
        if not self.db or not getattr(self.db, '_conn', None):
            return flags  # DB not connected
        all_kb = self.knowledge_agent.search_all(user_id=user_id)
        # needs_verify: single-source knowledge without evolution links
        for kb in all_kb[:50]:
            # H-3 fix: use store API instead of reaching into private _conn
            evo_count = self.db.count_evolution_for(kb["id"])
            if evo_count == 0:
                age = self._freshness(kb)
                if age > 0.3:  # still fresh but unverified
                    flags.append({"type": "needs_verify", "memory_type": "knowledge",
                                  "memory_id": kb["id"], "content": kb["content"][:120]})
        # contradiction: pairwise Jaccard scan
        ids = list(self.knowledge_agent.store.keys())[:30]
        for i in range(len(ids)):
            for j in range(i + 1, min(i + 10, len(ids))):
                a = self.knowledge_agent.store.get(ids[i])
                b = self.knowledge_agent.store.get(ids[j])
                if not a or not b:
                    continue
                sim = self._jaccard_similarity(a.content, b.content)
                if sim > 0.7 and self._detect_contradiction(a.content, b.content):
                    flags.append({"type": "contradiction", "memory_type": "knowledge",
                                  "memory_id": f"{ids[i]} vs {ids[j]}",
                                  "content": f"{a.content[:50]} ... {b.content[:50]}"})
        return flags

    _CONTRADICT_POS = ["use", "choose", "select", "recommend", "best", "optimal", "采用", "使用", "推荐"]
    _CONTRADICT_NEG = ["avoid", "not", "never", "wrong", "deprecated", "不要", "不应", "避免"]

    def _detect_contradiction(self, text_a: str, text_b: str) -> bool:
        """Heuristic polarity check: one text suggests using X, other suggests avoiding X."""
        a_l, b_l = text_a.lower(), text_b.lower()
        a_pos = any(w in a_l for w in self._CONTRADICT_POS)
        b_pos = any(w in b_l for w in self._CONTRADICT_POS)
        a_neg = any(w in a_l for w in self._CONTRADICT_NEG)
        b_neg = any(w in b_l for w in self._CONTRADICT_NEG)
        return (a_pos and b_neg) or (a_neg and b_pos)

    def _detect_knowledge_evolution(self, content: str, user_id: str, domain: str = "general",
                                    knowledge_id: str = "",
                                    origin_agent: str = "", origin_session_id: str = "",
                                    origin_turn: int = 0):
        """Scan existing knowledge via Jaccard, classify relations, write evolution records.

        origin_* fields are recorded on the evolution rows (provenance, migration v9)
        so the relationship can be traced to the agent/session/turn that produced it.
        """
        if not self._persistence_enabled or not content or len(content) < 20 or not knowledge_id:
            return
        try:
            candidates = self.knowledge_agent.search(query=content, user_id=user_id,
                                                      domain=domain, top_k=50)
            best_sim, best_id, best_content = 0.0, None, ""
            for c in candidates:
                sim = self._jaccard_similarity(content[:500], (c.get("content", "") or "")[:500])
                if sim > best_sim:
                    best_sim, best_id, best_content = sim, c.get("id"), c.get("content", "")
            if best_id == knowledge_id:
                return  # self-reference — skip evolution detection
            if best_sim > 0.7 and best_id:
                relation = self._llm_classify_relation(best_content or "", content, best_sim)
                if relation:
                    self.db.save_evolution(best_id, knowledge_id, relation,
                        confidence=best_sim, reason="jaccard_match",
                        detection_method="llm" if best_sim < 0.9 else "jaccard",
                        origin_agent=origin_agent, origin_session_id=origin_session_id,
                        origin_turn=origin_turn)
                    if relation == "replaces" and best_sim >= 0.9:
                        self.db.save_memory_state("knowledge", best_id, "superseded",
                            reason=f"replaced_by:{knowledge_id}", source="evolution")
        except Exception as e:
            logger.debug("Knowledge evolution detection skipped: %s", e)

    # ── P3-2: Entity extraction ────────────────────────

    def _extract_entities(self, content: str) -> List[Dict]:
        """Extract entities using LLM if available, keyword fallback otherwise."""
        llm = self._get_llm_client() if hasattr(self, '_get_llm_client') else None
        if llm:
            try:
                return self._llm_extract_entities(llm, content)
            except Exception:
                pass
        return self._keyword_extract_entities(content)

    def _llm_extract_entities(self, llm, content: str) -> List[Dict]:
        prompt = "Extract named entities (technologies, concepts, people, projects) from this text. Return JSON: [{\"type\":\"technology\",\"name\":\"...\"}]"
        result = llm.chat(f"{prompt}\n\n{content[:600]}", temperature=0, max_tokens=200)
        try:
            parsed = __import__('json').loads(result)
            if isinstance(parsed, list):
                for e in parsed:
                    e.setdefault("source", "llm")
                    e.setdefault("confidence", 0.85)
                return parsed
        except Exception:
            pass
        return self._keyword_extract_entities(content)

    def _keyword_extract_entities(self, content: str) -> List[Dict]:
        entities = []
        kw_cfg = self.cfg.get("entities", "technologies", default=[])
        if isinstance(kw_cfg, str):
            kw_cfg = [kw_cfg]
        for kw in kw_cfg:
            if isinstance(kw, str) and kw.lower() in content.lower():
                entities.append({"type": "technology", "name": kw, "confidence": 0.6, "source": "keyword"})
        return entities[:10]

    # ── Autoreflection score (P4-2 in autoreflection absorption) ──

    def compute_autoreflection_score(self) -> tuple:
        """Return (score_0_to_4, diagnostics_block) based on the 4 criteria from
        Lewis (2026): situated awareness, architectural congruence,
        analysis-from-architecture, incorporation-and-expansion.

        This is a heuristic self-assessment — zero LLM cost — so the agent or
        the developer can see how far the system has progressed from
        'telemetry' to true 'autoreflection'.
        """
        score = 0
        lines: list[str] = []

        # 1. Situated awareness: does the system know it runs inside an agentic harness?
        ref_config = self.reflective.config if hasattr(self, 'reflective') else {}
        if ref_config and self._persistence_enabled:
            score += 1
            lines.append("  ✅ C1: situated awareness — persistence active, reflection configured")
        else:
            lines.append("  ❌ C1: situated awareness — persistence or reflection missing")

        # 2. Architectural congruence: does it have enough data to describe its own state?
        try:
            stats = self.db.get_memory_stats()
            total_active = sum(s.get("active", 0) for s in stats.values())
            if total_active > 0:
                score += 1
                lines.append(f"  ✅ C2: architectural congruence — {total_active} active memory records")
            else:
                lines.append("  ❌ C2: architectural congruence — no active records")
        except Exception:
            lines.append("  ❌ C2: architectural congruence — DB unavailable")

        # 3. Analysis-from-architecture: do we have evidence that the system
        #    reasoned about its own state?  (proxied by: any reflection output)
        try:
            # H-3/W-3 fix: use the store API instead of reaching into private _conn
            ref_count = self.db.count_reflections()
            if ref_count > 0:
                score += 1
                lines.append(f"  ✅ C3: analysis-from-architecture — {ref_count} reflections recorded")
            else:
                lines.append("  ❌ C3: analysis-from-architecture — no reflection output")
        except Exception:
            lines.append("  ❌ C3: analysis-from-architecture — DB unavailable")

        # 4. Incorporation-and-expansion: have we incorporated external feedback?
        try:
            # (W-5) removed unused `cw` dead variable
            rl_updated = len(getattr(self.rl_optimizer, 'history', [])) > 0
            if rl_updated:
                score += 1
                lines.append(f"  ✅ C4: incorporation-and-expansion — RL weights active")
            else:
                lines.append("  ❌ C4: incorporation-and-expansion — no RL feedback loop")
        except Exception:
            lines.append("  ❌ C4: incorporation-and-expansion — RL unavailable")

        # Render a one-line summary
        if score <= 1:
            desc = "(telemetry only — not yet autoreflective)"
        elif score <= 2:
            desc = "(weak autoreflection — describe but not reason)"
        elif score <= 3:
            desc = "(approaching autoreflection — reasoning present, incorporation incomplete)"
        else:
            desc = "(autoreflective — all 4 criteria met)"

        summary = f"Autoreflection score: {score}/4 {desc}\n" + "\n".join(lines)
        return score, summary

    # ── Markdown Rendering (v1.2.9) ─────────────────────────────
    # Data extraction lives here; pure rendering lives in core/markdown_renderer.py.
    # _query_* methods extract structured data from the agent; export calls the renderer.

    def _query_archive_data(self, user_id: str, profile: str = "default"):
        """Build a MemoryArchive from the agent's current state."""
        from .markdown_renderer import MemoryArchive, KnowledgeRow, ExperienceRow, TaskRow
        from ._reflective_version import get_echomind_version

        # autoreflection
        try:
            score, summary = self.compute_autoreflection_score()
        except Exception:
            score, summary = 0, ""

        # user — V8-1: scope profile to avoid reading the default profile's
        # preferences/habits/history when an explicit profile was requested.
        u = self.user_agent.get(user_id, profile=profile)
        prefs = u.get("preferences", {}) if isinstance(u, dict) else {}
        habits = u.get("habits", {}) if isinstance(u, dict) else {}
        history = u.get("history", []) if isinstance(u, dict) else []

        # knowledge → KnowledgeRow list — V8-1: pass profile so the export
        # stays within the requested profile (was exporting every profile).
        knowledge: list = []
        for item in self.knowledge_agent.search_all(user_id=user_id, profile=profile):
            mode = item.get("metadata", {}).get("epistemic_mode", "")
            cog = item.get("metadata", {}).get("cognitive_pos", "")
            trust = item.get("metadata", {}).get("trust_score", 0.5)
            domain = (item.get("domain") or
                      item.get("metadata", {}).get("category", "general"))
            # V8-5: guard against non-numeric trust_score in raw metadata —
            # float("high") would crash the whole export. Fall back to 0.5.
            try:
                trust_f = float(trust) if trust else 0.5
            except (TypeError, ValueError):
                trust_f = 0.5
            knowledge.append(KnowledgeRow(
                content=item.get("content", "") or "",
                trust_score=trust_f,
                epistemic_mode=mode or "",
                cognitive_pos=cog or "",
                domain=domain or "general",
            ))

        # experience → ExperienceRow list
        # V8-2 fix: an empty task_context previously made find_similar_tasks
        # return [] (tokenize("") → [] → any() = False), so the experience
        # section was always empty. Let find_similar_tasks treat an empty
        # context as "enumerate all matching candidates". V8-1: pass profile.
        experience: list = []
        for e in self.experience_agent.find_similar_tasks(
            task_context="", task_type="", user_id=user_id, profile=profile,
            min_success_rate=0.0, limit=50,
        ):
            experience.append(ExperienceRow(
                summary=e.get("summary", "") or "",
                frequency=e.get("frequency", 1),
                success=bool(e.get("success")),
            ))

        # tasks → TaskRow list — V8-1: filter by profile as well (the task
        # store carries a profile per entry; only export the requested one).
        tasks: list = [
            TaskRow(title=t.title, status=t.status)
            for t in self.task_agent.store.values()
            if t.user_id == user_id and t.profile == profile
        ]

        # research — V8-1: scope papers to the requested user/profile
        papers: list = [
            p for p in self.research_agent.papers.values()
            if p.user_id == user_id and p.profile == profile
        ]

        # stats — K2 fix: build header counts from the SAME profile-scoped data
        # that renders below. The previous get_memory_stats() reported GLOBAL
        # counts across every profile while the sections below are scoped to
        # this profile, making the header self-contradict for non-default
        # profiles. The archive presents current entries only, so lifecycle
        # state is collapsed to active (the health report uses get_memory_stats).
        stats = {
            "knowledge": {"active": len(knowledge), "stale": 0, "archived": 0},
            "experience": {"active": len(experience), "stale": 0, "archived": 0},
            "task": {"active": len(tasks), "stale": 0, "archived": 0},
            "paper": {"active": len(papers), "stale": 0, "archived": 0},
            "user": {"active": 1, "stale": 0, "archived": 0},
            "context": {"active": len(self.context_agent._sessions),
                        "stale": 0, "archived": 0},
        }

        # reflection — V8-3: filter by user_id so we never leak another
        # user's latest reflection into this archive. Reflections have no
        # profile column, so user_id is the only isolation dimension here.
        ref_conf = 0.0
        ref_insights = ""
        ref_knowledge = ""
        try:
            # V8-9: use the public store API (get_latest_reflection) instead of
            # reaching into the private _conn. It also scopes by user_id (V8-3).
            if self.is_persistence_enabled():
                row = self.db.get_latest_reflection(user_id)
                if row:
                    ref_conf = float(row.get("confidence") or 0.0)
                    ref_insights = row.get("key_insights") or ""
                    ref_knowledge = row.get("new_knowledge") or ""
        except Exception:
            pass

        return MemoryArchive(
            version=get_echomind_version(),
            generated_at=datetime.now(timezone.utc).isoformat(),
            autoreflection_score=score,
            autoreflection_summary=summary,
            stats=stats,
            user_prefs=prefs,
            user_habits=habits,
            user_history=history,
            knowledge=knowledge,
            experience=experience,
            tasks=tasks,
            papers=papers,
            reflection_confidence=ref_conf,
            reflection_insights=ref_insights,
            reflection_knowledge=ref_knowledge,
        )

    def export_memory_to_markdown(self, user_id: str, profile: str = "default") -> str:
        data = self._query_archive_data(user_id, profile)
        from .markdown_renderer import render_full_archive
        return render_full_archive(data)
