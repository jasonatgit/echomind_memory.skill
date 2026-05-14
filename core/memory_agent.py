# echomind_memory.skill/memory_agent.py

import json
import uuid
from datetime import datetime
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


class MemoryRecord(BaseModel):
    source: str
    content: str
    importance: float
    metadata: Dict[str, Any]


class ContextMemoryAgent:
    def __init__(self):
        self.memory = ContextMemory()

    def add_message(self, message: Dict[str, str]) -> None:
        msg = ContextMessage(**message)
        self.memory.messages.append(msg)
        if len(self.memory.messages) > self.memory.window_size:
            self.memory.messages.pop(0)

    def get_context(self) -> List[Dict[str, str]]:
        return [{"role": m.role, "content": m.content} for m in self.memory.messages]

    def clear(self) -> None:
        self.memory.messages = []


class TaskMemoryAgent:
    def __init__(self):
        self.store: Dict[str, TaskMemory] = {}

    def create_task(self, user_id: str, task_id: str, title: str, steps: List[Dict]) -> str:
        task = TaskMemory(
            user_id=user_id, task_id=task_id, title=title, status="pending", steps=steps,
        )
        self.store[task_id] = task
        logger.info(f"Task created: {task_id}")
        return task.id

    def update_step(self, task_id: str, step_index: int, status: str, result: str) -> bool:
        if task_id not in self.store:
            return False
        task = self.store[task_id]
        if step_index >= len(task.steps):
            return False
        task.steps[step_index]["status"] = status
        task.steps[step_index]["result"] = result
        task.updated_at = datetime.utcnow()
        return True

    def get_task_progress(self, task_id: str) -> Optional[Dict]:
        if task_id not in self.store:
            return None
        task = self.store[task_id]
        return {
            "status": task.status, "steps": task.steps,
            "title": task.title, "updated_at": task.updated_at.isoformat(),
        }

    def get_recent_tasks(self, user_id: str, task_type: str, limit: int = 5) -> List[Dict]:
        tasks = [t for t in self.store.values()
                 if t.user_id == user_id and t.metadata.get("task_type") == task_type]
        tasks.sort(key=lambda x: x.updated_at, reverse=True)
        return [{"task_id": t.task_id, "title": t.title, "status": t.status} for t in tasks[:limit]]


class UserMemoryAgent:
    def __init__(self):
        self.store: Dict[str, UserMemory] = {}
        self.cache: Dict[str, UserMemory] = {}

    def get(self, user_id: str, platform: str = None) -> Dict[str, Any]:
        if user_id in self.cache:
            mem = self.cache[user_id]
            return self._extract_platform_prefs(mem, platform)
        if user_id not in self.store:
            self.store[user_id] = UserMemory(user_id=user_id)
        mem = self.store[user_id]
        self.cache[user_id] = mem
        return self._extract_platform_prefs(mem, platform)

    def _extract_platform_prefs(self, mem: UserMemory, platform: str) -> Dict[str, Any]:
        """从 platform-aware 的 preferences JSON 中提取当前平台的偏好"""
        raw = mem.dict()
        prefs = raw.get("preferences", {})
        if isinstance(prefs, dict) and "_default" in prefs:
            # v3.0+ platform-aware 格式
            merged = dict(prefs.get("_default", {}))
            if platform and platform in prefs:
                merged.update(prefs.get(platform, {}))
            raw["preferences"] = merged
        # else: pre-v3.0 旧格式，直接返回
        return raw

    def update(self, user_id: str, key: str, value: Any,
               source: str = "implicit", platform: str = None) -> bool:
        if user_id not in self.store:
            self.store[user_id] = UserMemory(user_id=user_id)
        mem = self.store[user_id]
        if key in ["preferences", "habits"]:
            (getattr(mem, key).update({value: True})
             if isinstance(value, str) else getattr(mem, key).update(value))
        elif key == "history":
            mem.history.append({"timestamp": datetime.utcnow().isoformat(), "action": value})
        else:
            setattr(mem, key, value)
        mem.version += 1
        mem.last_updated = datetime.utcnow()
        self.cache[user_id] = mem
        return True


class KnowledgeMemoryAgent:
    def __init__(self):
        self.store: Dict[str, KnowledgeEntry] = {}

    def search(self, query: str, domain: str = None, top_k: int = 5) -> List[Dict]:
        results = []
        for entry in self.store.values():
            if domain and entry.metadata.get("category") != domain:
                continue
            if query.lower() in entry.content.lower() or any(
                w in entry.content.lower() for w in query.split()[:2]
            ):
                relevance = 0.8 if query.lower() in entry.content.lower() else 0.5
                results.append({"id": entry.id, "content": entry.content,
                                "metadata": entry.metadata, "relevance": relevance})
        results.sort(key=lambda x: x["relevance"], reverse=True)
        return results[:top_k]

    def add_document(self, content: str, metadata: Dict) -> str:
        entry = KnowledgeEntry(content=content, metadata=metadata)
        self.store[entry.id] = entry
        return entry.id


class ExperienceMemoryAgent:
    def __init__(self):
        self.store: Dict[str, ExperienceEntry] = {}

    def store_experience(self, task_id: str, success: bool, steps: List[str], summary: str) -> str:
        entry = ExperienceEntry(
            user_id="temp_user", task_type="default_task",
            success=success, steps_sequence=steps, summary=summary,
        )
        self.store[entry.id] = entry
        return entry.id

    def find_similar_tasks(self, task_context: str, task_type: str,
                           min_success_rate: float = 0.7, limit: int = 3) -> List[Dict]:
        similar = []
        for entry in self.store.values():
            if entry.task_type != task_type or entry.success < min_success_rate:
                continue
            if any(k in entry.summary.lower() for k in task_context.lower().split()[:3]):
                similar.append({
                    "id": entry.id, "summary": entry.summary,
                    "steps": entry.steps_sequence, "success": entry.success,
                    "frequency": entry.frequency,
                })
        similar.sort(key=lambda x: x["frequency"], reverse=True)
        return similar[:limit]


from .learning.rl_weight_optimizer import RLWeightOptimizer
from .storage.sqlite_store import SqliteStore


class ResearchMemoryAgent:
    def __init__(self):
        self.papers: Dict[str, ResearchPaper] = {}
        self.notes: Dict[str, ResearchNote] = {}
        self.ms_domains = [
            "operations_research", "supply_chain", "decision_analysis",
            "optimization", "simulation", "queuing_theory",
            "game_theory", "forecasting", "project_management",
            "quality_management", "data_analytics", "system_dynamics",
        ]

    def add_paper(self, paper: ResearchPaper) -> str:
        self.papers[paper.id] = paper
        logger.info(f"[Research] 添加论文: {paper.title}")
        return paper.id

    def search_papers(self, query: str, domain: str = None, top_k: int = 5) -> List[Dict[str, Any]]:
        results = []
        q_lower = query.lower()
        for p in self.papers.values():
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
        logger.info(f"[Research] 添加笔记: {note.topic}")
        return note.id

    def search_notes(self, query: str, tags: List[str] = None, top_k: int = 3) -> List[Dict]:
        results = []
        q_lower = query.lower()
        for n in self.notes.values():
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


class MainMemoryAgent:
    def __init__(self, db_path: str = None):
        self.context_agent = ContextMemoryAgent()
        self.task_agent = TaskMemoryAgent()
        self.user_agent = UserMemoryAgent()
        self.knowledge_agent = KnowledgeMemoryAgent()
        self.experience_agent = ExperienceMemoryAgent()
        self.research_agent = ResearchMemoryAgent()
        self.db = SqliteStore(db_path)
        self.rl_optimizer = RLWeightOptimizer(
            initial_weights={
                "relevance": 0.4, "recency": 0.2, "frequency": 0.15,
                "explicit_feedback": 0.15, "trust_score": 0.1,
            },
            learning_rate=0.07, decay_factor=0.97,
        )
        self._persistence_enabled = False

    def enable_persistence(self):
        self.db.connect()
        self.db.ensure_tables()
        self._persistence_enabled = True
        self._load_from_db()  # 启动时加载历史记忆
        logger.info("SQLite persistence enabled (7 tables, 6 memory types loaded)")

    def _load_from_db(self):
        """从 SQLite 恢复全部记忆到内存 Agent"""
        all_data = self.db.load_all()
        loaded = {"users": 0, "tasks": 0, "experiences": 0, "contexts": 0,
                   "knowledge": 0, "papers": 0, "notes": 0}

        # 1. 用户记忆
        for u in all_data.get("users", []):
            uid = u["user_id"]
            self.user_agent.store[uid] = UserMemory(
                user_id=uid, preferences=u["preferences"],
                habits=u["habits"], history=u["history"],
                version=u.get("version", 1))
            self.user_agent.cache[uid] = self.user_agent.store[uid]
            loaded["users"] += 1

        # 2. 任务记忆
        for t in all_data.get("tasks", []):
            task = TaskMemory(
                user_id=t["user_id"], task_id=t.get("id", ""),
                title=t.get("title",""), status=t.get("status","pending"),
                steps=t.get("steps",[]))
            task.metadata = t.get("metadata", {})
            self.task_agent.store[t.get("id", "")] = task
            loaded["tasks"] += 1

        # 3. 经验记忆
        for e in all_data.get("experiences", []):
            exp = ExperienceEntry(
                user_id=e.get("user_id",""), task_type=e.get("task_type","default"),
                success=bool(e.get("success",0)),
                steps_sequence=e.get("steps_sequence",[]),
                summary=e.get("summary",""))
            self.experience_agent.store[e.get("id","")] = exp
            loaded["experiences"] += 1

        # 4. 上下文记忆（恢复最近一次会话）
        for c in all_data.get("contexts", []):
            messages = c.get("messages", [])
            for msg in messages:
                if isinstance(msg, dict) and "role" in msg:
                    self.context_agent.add_message(msg)
            loaded["contexts"] += 1

        # 5. 知识记忆
        for k in all_data.get("knowledge", []):
            entry = KnowledgeEntry(
                content=k.get("content",""),
                metadata=k.get("metadata",{}))
            entry.id = k.get("id", entry.id)
            self.knowledge_agent.store[entry.id] = entry
            loaded["knowledge"] += 1

        # 6. 研究论文
        for p in all_data.get("research_papers", []):
            paper = ResearchPaper(
                id=p.get("id",""), title=p.get("title",""),
                authors=p.get("authors",[]), year=p.get("year"),
                journal=p.get("journal",""), abstract=p.get("abstract",""),
                keywords=p.get("keywords",[]), domain=p.get("domain","general"),
                paper_type=p.get("paper_type","theory"),
                key_points=p.get("key_points",[]),
                importance_score=p.get("importance_score",0.5))
            self.research_agent.papers[paper.id] = paper
            loaded["papers"] += 1

        # 7. 研究笔记
        for n in all_data.get("research_notes", []):
            note = ResearchNote(id=n.get("id",""), user_id=n.get("user_id",""),
                topic=n.get("topic",""), content=n.get("content",""),
                linked_papers=n.get("linked_papers",[]),
                tags=n.get("tags",[]))
            self.research_agent.notes[note.id] = note
            loaded["notes"] += 1

        if sum(loaded.values()) > 0:
            logger.info(f"Loaded from DB: {loaded}")
        else:
            logger.info("Empty DB — fresh start")

        # 8. RL 权重恢复
        saved_weights = self.db.load_rl_weights("default")
        if saved_weights:
            self.rl_optimizer.weights = saved_weights
            self.rl_optimizer.ema_weights = saved_weights.copy()
            logger.info(f"RL weights restored: {saved_weights}")

    def disable_persistence(self):
        self._persistence_enabled = False

    def _extract_task_features(self, task_context: str) -> Dict[str, Any]:
        research_keywords = [
            "管理科学", "运筹学", "供应链", "决策分析", "优化模型",
            "simulation", "queueing", "game theory", "forecasting",
            "operations research", "supply chain", "系统工程",
            "管理科学与工程", "论文", "文献", "研究综述",
            "literature", "review", "contract", "coordination",
        ]
        features = {
            "requires_knowledge": any(k in task_context.lower() for k in ["分析", "报告", "数据", "研究"]),
            "is_complex": any(k in task_context.lower() for k in ["详细", "深度", "对比", "综合"]),
            "has_history": any(k in task_context.lower() for k in ["上次", "之前", "继续", "接着", "之前做的"]),
            "domain": "finance" if any(k in task_context.lower() for k in ["财务", "预算", "报销", "投资"]) else "general",
            "task_type": "analysis" if any(k in task_context.lower() for k in ["分析", "报告"]) else "general",
            "requires_research": any(k in task_context.lower() for k in research_keywords),
            "research_domain": self._detect_research_domain(task_context),
        }
        return features

    def _detect_research_domain(self, text: str) -> str:
        domain_map = {
            "operations_research": ["运筹学", "线性规划", "整数规划", "operations research"],
            "supply_chain": ["供应链", "库存", "物流", "supply chain"],
            "decision_analysis": ["决策分析", "多准则", "ahp", "decision analysis"],
            "optimization": ["优化", "最优", "梯度", "optimization"],
            "simulation": ["仿真", "模拟", "蒙特卡洛", "simulation"],
            "game_theory": ["博弈论", "纳什均衡", "game theory"],
            "forecasting": ["预测", "时间序列", "forecasting"],
            "project_management": ["项目管理", "关键路径", "project management"],
            "queuing_theory": ["排队论", "队列", "queuing"],
        }
        t = text.lower()
        for domain, keywords in domain_map.items():
            if any(k in t for k in keywords):
                return domain
        return "general"

    def retrieve_for_task(self, task_context: str, user_id: str,
                         task_id: Optional[str] = None,
                         platform: Optional[str] = None) -> Dict[str, Any]:
        logger.info(f"Retrieving memory for task: {task_context[:50]}...")
        features = self._extract_task_features(task_context)
        retrieved = {}

        retrieved["user"] = self.user_agent.get(user_id, platform=platform)

        if features["requires_knowledge"]:
            retrieved["knowledge"] = self.knowledge_agent.search(
                query=task_context, domain=features["domain"], top_k=5)
        if features["is_complex"]:
            retrieved["experience"] = self.experience_agent.find_similar_tasks(
                task_context=task_context, task_type=features["task_type"],
                min_success_rate=0.7, limit=3)
        if features["has_history"]:
            if task_id:
                retrieved["task_progress"] = self.task_agent.get_task_progress(task_id)
            else:
                retrieved["task_history"] = self.task_agent.get_recent_tasks(
                    user_id=user_id, task_type=features["task_type"], limit=5)
        if features.get("requires_research"):
            retrieved["research"] = self.research_agent.search_papers(
                query=task_context, domain=features.get("research_domain"), top_k=5)

        # 6. 上下文记忆检索（总是检索，取最近 2 个会话）
        if self._persistence_enabled:
            recent_contexts = self.db.search_context(user_id, platform=platform, limit=2)
            if recent_contexts:
                retrieved["context"] = recent_contexts

        scored = self._compute_importance(retrieved, task_context, user_id, platform)
        top_memories = sorted(scored, key=lambda x: x.importance, reverse=True)[:8]

        return {
            "working_memory": top_memories,
            "raw_memory_sources": retrieved,
            "task_features": features,
            "feedback_request": True,
            "retrieved_memories": top_memories,
        }

    def _compute_importance(self, retrieved: Dict[str, Any], query: str,
                            user_id: str, platform: Optional[str] = None) -> List[MemoryRecord]:
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
                        age = (datetime.utcnow() - datetime.fromisoformat(mem["metadata"]["last_updated"])).days
                        recency = max(0, 1 - age / 30)
                    trust = mem["metadata"].get("trust_score", 0.5)
                    score = relevance * weights["relevance"] + recency * weights["recency"] + trust * weights["trust_score"]
                    scored.append(MemoryRecord(source=source, content=mem["content"], importance=round(score, 3), metadata=mem))

            elif source == "experience":
                for mem in memories:
                    score = 0.6 * weights["relevance"] + mem["frequency"] * weights["frequency"] + 0.5 * weights["recency"]
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
                    score = mem["relevance"] * weights["relevance"] + mem["importance_score"] * 0.3
                    key_points_str = "; ".join(mem.get("key_points", [])[:3])
                    scored.append(MemoryRecord(
                        source=source,
                        content=f"[{mem.get('domain','general')}] {mem['title']}: {key_points_str}",
                        importance=round(score, 3), metadata=mem,
                    ))

            elif source == "context":
                for ctx in memories:
                    messages = ctx.get("messages", [])
                    preview = " ".join(
                        m.get("content", "")[:60] for m in messages
                        if m.get("role") in ("user", "assistant")
                    )[:200]
                    if preview:
                        # Platform-aware weighting: 同平台 ×1.0, 跨平台 ×0.5
                        ctx_platform = ctx.get("platform", "")
                        platform_mult = 1.0 if (not platform or ctx_platform == platform) else 0.5
                        scored.append(MemoryRecord(
                            source="context",
                            content=f"[{ctx_platform or 'unknown'}] Previous session: {preview}",
                            importance=round(0.7 * platform_mult, 3),
                            metadata={"session_id": ctx.get("session_id", ""),
                                      "platform": ctx_platform},
                        ))

        return scored

    def store(self, user_id: str, task_id: str, context: List[Dict],
              task_status: str, success: bool = False, experience_summary: str = None,
              platform: str = None):
        for msg in context:
            self.context_agent.add_message(msg)
        self.task_agent.create_task(user_id=user_id, task_id=task_id, title="自动任务",
                                    steps=[{"step": "初始化", "status": task_status}])
        self._infer_user_preferences(context, user_id)

        if self._persistence_enabled:
            user_data = self.user_agent.get(user_id, platform=platform)
            self.db.save_user(user_id,
                preferences=user_data.get("preferences", {}),
                habits=user_data.get("habits", {}),
                history=user_data.get("history", []),
                platform=platform)
            self.db.save_task(user_id, task_id, "自动任务", task_status,
                              steps=[{"step": "初始化", "status": task_status}])
            # 保存上下文记忆（带 platform 标签）
            self.db.save_context(
                session_id=f"{user_id}:{task_id}",
                user_id=user_id,
                messages=context,
                token_count=sum(len(m.get("content","")) for m in context) // 4,
                platform=platform or "default")
            # 如果有领域关键词，保存知识条目
            features = self._extract_task_features(
                " ".join(m.get("content","") for m in context if m.get("role")=="user"))
            research_domain = features.get("research_domain", "general")
            if research_domain != "general":
                self.db.save_knowledge(
                    knowledge_id=f"{user_id}:{task_id}",
                    domain=research_domain,
                    content=experience_summary or "自动提取的知识",
                    metadata={"source": "task", "task_id": task_id})

        if success or experience_summary:
            steps_from_context = [m["content"] for m in context if m["role"] != "system"]
            self.experience_agent.store_experience(
                task_id=task_id, success=success, steps=steps_from_context,
                summary=experience_summary or "系统自动生成的经验总结",
            )
            if self._persistence_enabled:
                self.db.save_experience(user_id, "default_task", success, steps_from_context,
                                        experience_summary or "系统自动生成的经验总结")

    def add_research_paper(self, title: str, authors: List[str] = None, year: int = None,
                           journal: str = None, abstract: str = "", keywords: List[str] = None,
                           domain: str = "general", paper_type: str = "theory",
                           key_points: List[str] = None, importance_score: float = 0.5) -> str:
        """添加研究论文到内存和持久化"""
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
        """添加研究笔记到内存和持久化"""
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

    def _infer_user_preferences(self, context: List[Dict], user_id: str):
        concise_count = sum(1 for msg in context if "简短" in msg["content"] or "简洁" in msg["content"])
        if concise_count >= 2:
            self.user_agent.update(user_id, "response_style", "concise", source="implicit")
        if any("type hint" in msg["content"] for msg in context) or any(
            "Optional[str]" in msg["content"] for msg in context
        ):
            self.user_agent.update(user_id, "code_style", "detailed", source="implicit")
        elif any("简洁" in msg["content"] for msg in context) or any(
            "不要注释" in msg["content"] for msg in context
        ):
            self.user_agent.update(user_id, "code_style", "concise", source="implicit")

    def record_feedback(self, user_id: str, task_id: str, feedback: str, retrieved_memories: List[Dict]):
        if feedback not in ["positive", "negative"]:
            raise ValueError("feedback must be 'positive' or 'negative'")
        from learning.rl_weight_optimizer import FeedbackRecord
        feedback_record = FeedbackRecord(
            user_id=user_id, task_id=task_id,
            retrieved_memories=retrieved_memories, user_feedback=feedback,
        )
        self.rl_optimizer.add_feedback(feedback_record)
        # 持久化 RL 权重
        if self._persistence_enabled:
            self.db.save_rl_weights("default", self.rl_optimizer.weights)
        logger.info(f"User {user_id} gave {feedback} feedback on task {task_id}")

    def sync_to_code_project(self, project_root: str, user_id: str):
        from pathlib import Path
        echomind_dir = Path(project_root) / ".echomind"
        echomind_dir.mkdir(exist_ok=True)

        user_mem = self.user_agent.get(user_id)
        exp_mem = self.experience_agent.find_similar_tasks(
            task_context=f"代码风格偏好: {user_mem.get('preferences', {}).get('code_style', 'standard')}",
            task_type="code_review", min_success_rate=0.6,
        )

        config = {
            "user_preferences": user_mem.get("preferences", {}),
            "user_habits": user_mem.get("habits", {}),
            "recent_code_experience": exp_mem[:3],
            "updated_at": datetime.utcnow().isoformat(),
        }
        (echomind_dir / "context.json").write_text(
            json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")

        summary = "=== EchoMind 记忆摘要 ===\n"
        style = user_mem.get("preferences", {}).get("code_style")
        if style == "concise":
            summary += "▸ 你的代码风格偏好：简洁、无注释、函数短小\n"
        elif style == "detailed":
            summary += "▸ 你的代码风格偏好：详尽注释、文档优先、模块化\n"
        for exp in exp_mem[:2]:
            summary += f"\n▸ 你曾成功修复：{exp['summary']}\n"
        for rp in list(self.research_agent.papers.values())[:3]:
            summary += f"\n▸ 研究论文：{rp.title}（{rp.domain}）\n"
        (echomind_dir / "README.md").write_text(summary, encoding="utf-8")
        logger.info(f"Synced EchoMind memories to {echomind_dir}")

    def get_context(self) -> List[Dict]:
        return self.context_agent.get_context()

    def clear_context(self):
        self.context_agent.clear()