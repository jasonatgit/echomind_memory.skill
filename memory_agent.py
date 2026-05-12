# echomind_memory.skill/memory_agent.py

import asyncio
import uuid
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import logging

# ========================
# 日志配置
# ========================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MemoryAgent")

# ========================
# 数据模型（从 models 包导入，消除重复）
# ========================

from models.context import ContextMessage, ContextMemory
from models.task import TaskMemory
from models.user import UserMemory
from models.knowledge import KnowledgeEntry
from models.experience import ExperienceEntry
from models.research import ResearchPaper, ResearchNote


class MemoryRecord(BaseModel):
    source: str
    content: str
    importance: float
    metadata: Dict[str, Any]


# ========================
# 子 Agent 实现
# ========================


class ContextMemoryAgent:
    def __init__(self):
        self.memory = ContextMemory()

    async def add_message(self, message: Dict[str, str]) -> None:
        msg = ContextMessage(**message)
        self.memory.messages.append(msg)

        if len(self.memory.messages) > self.memory.window_size:
            self.memory.messages.pop(0)

    async def get_context(self) -> List[Dict[str, str]]:
        return [{"role": m.role, "content": m.content} for m in self.memory.messages]

    async def clear(self) -> None:
        self.memory.messages = []


class TaskMemoryAgent:
    def __init__(self):
        self.store: Dict[str, TaskMemory] = {}

    async def create_task(
        self, user_id: str, task_id: str, title: str, steps: List[Dict]
    ) -> str:
        task = TaskMemory(
            user_id=user_id,
            task_id=task_id,
            title=title,
            status="pending",
            steps=steps,
        )
        self.store[task_id] = task
        logger.info(f"Task created: {task_id}")
        return task.id

    async def update_step(
        self, task_id: str, step_index: int, status: str, result: str
    ) -> bool:
        if task_id not in self.store:
            return False
        task = self.store[task_id]
        if step_index >= len(task.steps):
            return False
        task.steps[step_index]["status"] = status
        task.steps[step_index]["result"] = result
        task.updated_at = datetime.utcnow()
        logger.info(f"Updated step {step_index} of task {task_id} to {status}")
        return True

    async def get_task_progress(self, task_id: str) -> Optional[Dict]:
        if task_id not in self.store:
            return None
        task = self.store[task_id]
        return {
            "status": task.status,
            "steps": task.steps,
            "title": task.title,
            "updated_at": task.updated_at.isoformat(),
        }

    async def get_recent_tasks(
        self, user_id: str, task_type: str, limit: int = 5
    ) -> List[Dict]:
        tasks = [
            t
            for t in self.store.values()
            if t.user_id == user_id and t.metadata.get("task_type") == task_type
        ]
        tasks.sort(key=lambda x: x.updated_at, reverse=True)
        return [
            {"task_id": t.task_id, "title": t.title, "status": t.status}
            for t in tasks[:limit]
        ]


class UserMemoryAgent:
    def __init__(self):
        self.store: Dict[str, UserMemory] = {}
        self.cache: Dict[str, UserMemory] = {}

    async def get(self, user_id: str) -> Dict[str, Any]:
        if user_id in self.cache:
            logger.info(f"UserMemory cache hit for {user_id}")
            return self.cache[user_id].dict()
        if user_id not in self.store:
            self.store[user_id] = UserMemory(user_id=user_id)
        mem = self.store[user_id]
        self.cache[user_id] = mem
        return mem.dict()

    async def update(
        self, user_id: str, key: str, value: Any, source: str = "implicit"
    ) -> bool:
        if user_id not in self.store:
            self.store[user_id] = UserMemory(user_id=user_id)
        mem = self.store[user_id]
        if key in ["preferences", "habits"]:
            (
                getattr(mem, key).update({value: True})
                if isinstance(value, str)
                else getattr(mem, key).update(value)
            )
        elif key == "history":
            mem.history.append(
                {"timestamp": datetime.utcnow().isoformat(), "action": value}
            )
        else:
            setattr(mem, key, value)
        mem.version += 1
        mem.last_updated = datetime.utcnow()
        self.cache[user_id] = mem
        logger.info(f"Updated user {user_id} {key}={value} (source: {source})")
        return True


class KnowledgeMemoryAgent:
    def __init__(self):
        self.store: Dict[str, KnowledgeEntry] = {}

    async def search(
        self, query: str, domain: str = None, top_k: int = 5
    ) -> List[Dict]:
        results = []
        for entry in self.store.values():
            if domain and entry.metadata.get("category") != domain:
                continue
            if query.lower() in entry.content.lower() or any(
                w in entry.content.lower() for w in query.split()[:2]
            ):
                relevance = 0.8 if query.lower() in entry.content.lower() else 0.5
                results.append(
                    {
                        "id": entry.id,
                        "content": entry.content,
                        "metadata": entry.metadata,
                        "relevance": relevance,
                    }
                )

        results.sort(key=lambda x: x["relevance"], reverse=True)
        return results[:top_k]

    async def add_document(self, content: str, metadata: Dict) -> str:
        entry = KnowledgeEntry(content=content, metadata=metadata)
        self.store[entry.id] = entry
        logger.info(f"Added knowledge doc: {entry.id}")
        return entry.id


class ExperienceMemoryAgent:
    def __init__(self):
        self.store: Dict[str, ExperienceEntry] = {}

    async def store_experience(
        self, task_id: str, success: bool, steps: List[str], summary: str
    ) -> str:
        task_type = "default_task"
        entry = ExperienceEntry(
            user_id="temp_user",
            task_type=task_type,
            success=success,
            steps_sequence=steps,
            summary=summary,
        )
        self.store[entry.id] = entry
        logger.info(
            f"Stored experience: {entry.id} ({'success' if success else 'failure'})"
        )
        return entry.id

    async def find_similar_tasks(
        self,
        task_context: str,
        task_type: str,
        min_success_rate: float = 0.7,
        limit: int = 3,
    ) -> List[Dict]:
        similar = []
        for entry in self.store.values():
            if entry.task_type != task_type:
                continue
            if entry.success < min_success_rate:
                continue
            if any(
                k in entry.summary.lower() for k in task_context.lower().split()[:3]
            ):
                similar.append(
                    {
                        "id": entry.id,
                        "summary": entry.summary,
                        "steps": entry.steps_sequence,
                        "success": entry.success,
                        "frequency": entry.frequency,
                    }
                )
        similar.sort(key=lambda x: x["frequency"], reverse=True)
        return similar[:limit]


# ========================
# RL 权重优化器（新增）
# ========================

from learning.rl_weight_optimizer import RLWeightOptimizer
from storage.postgres import PostgresStore

# ========================
# 研究记忆 Agent（新增：管理科学与工程领域）
# ========================


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

    async def add_paper(self, paper: ResearchPaper) -> str:
        self.papers[paper.id] = paper
        logger.info(f"[Research] 添加论文: {paper.title}")
        return paper.id

    async def search_papers(
        self, query: str, domain: str = None, top_k: int = 5
    ) -> List[Dict[str, Any]]:
        results = []
        q_lower = query.lower()
        for p in self.papers.values():
            if domain and p.domain != domain:
                continue
            relevance = 0.0
            if q_lower in p.title.lower():
                relevance = 0.9
            elif any(kw in q_lower for kw in p.keywords):
                relevance = 0.8
            elif q_lower in p.abstract.lower():
                relevance = 0.6
            elif any(kw in p.keywords for kw in query.split()):
                relevance = 0.4
            if relevance > 0:
                results.append({
                    "id": p.id,
                    "title": p.title,
                    "abstract": p.abstract,
                    "keywords": p.keywords,
                    "domain": p.domain,
                    "paper_type": p.paper_type,
                    "key_points": p.key_points,
                    "importance_score": p.importance_score,
                    "relevance": relevance,
                })
        results.sort(key=lambda x: x["relevance"] * x["importance_score"], reverse=True)
        return results[:top_k]

    async def add_note(self, note: ResearchNote) -> str:
        self.notes[note.id] = note
        logger.info(f"[Research] 添加笔记: {note.topic}")
        return note.id

    async def search_notes(
        self, query: str, tags: List[str] = None, top_k: int = 3
    ) -> List[Dict]:
        results = []
        q_lower = query.lower()
        for n in self.notes.values():
            if tags and not any(t in n.tags for t in tags):
                continue
            relevance = 1.0 if q_lower in n.content.lower() else 0.3
            results.append({
                "id": n.id,
                "topic": n.topic,
                "content": n.content,
                "tags": n.tags,
                "relevance": relevance,
            })
        results.sort(key=lambda x: x["relevance"], reverse=True)
        return results[:top_k]

    async def get_domain_overview(self, domain: str) -> List[Dict]:
        papers = [p for p in self.papers.values() if p.domain == domain]
        return [
            {
                "title": p.title,
                "keywords": p.keywords,
                "paper_type": p.paper_type,
                "key_points": p.key_points,
            }
            for p in papers[:10]
        ]


# ========================
# 主控 Agent
# ========================


class MainMemoryAgent:
    def __init__(self, dsn: str = "postgresql://agent:agent123@localhost:5432/agent_memory"):
        self.context_agent = ContextMemoryAgent()
        self.task_agent = TaskMemoryAgent()
        self.user_agent = UserMemoryAgent()
        self.knowledge_agent = KnowledgeMemoryAgent()
        self.experience_agent = ExperienceMemoryAgent()
        self.research_agent = ResearchMemoryAgent()
        self.pg = PostgresStore(dsn)
        self.rl_optimizer = RLWeightOptimizer(
            initial_weights={
                "relevance": 0.4,
                "recency": 0.2,
                "frequency": 0.15,
                "explicit_feedback": 0.15,
                "trust_score": 0.1,
            },
            learning_rate=0.07,
            decay_factor=0.97,
        )
        self._persistence_enabled = False

    async def enable_persistence(self):
        await self.pg.connect()
        if self.pg._conn:
            await self.pg.ensure_tables()
            self._persistence_enabled = True
            logger.info("PostgreSQL persistence enabled")

    async def _extract_task_features(self, task_context: str) -> Dict[str, Any]:
        research_keywords = [
            "管理科学", "运筹学", "供应链", "决策分析", "优化模型",
            "simulation", "queueing", "game theory", "forecasting",
            "operations research", "supply chain", "系统工程",
            "管理科学与工程", "论文", "文献", "研究综述",
        ]
        features = {
            "requires_knowledge": any(
                k in task_context.lower() for k in ["分析", "报告", "数据", "研究"]
            ),
            "is_complex": any(
                k in task_context.lower() for k in ["详细", "深度", "对比", "综合"]
            ),
            "has_history": any(
                k in task_context.lower()
                for k in ["上次", "之前", "继续", "接着", "之前做的"]
            ),
            "domain": (
                "finance"
                if any(
                    k in task_context.lower() for k in ["财务", "预算", "报销", "投资"]
                )
                else "general"
            ),
            "task_type": (
                "analysis"
                if any(k in task_context.lower() for k in ["分析", "报告"])
                else "general"
            ),
            "requires_research": any(
                k in task_context.lower() for k in research_keywords
            ),
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

    async def retrieve_for_task(
        self, task_context: str, user_id: str, task_id: Optional[str] = None
    ) -> Dict[str, Any]:
        logger.info(f"Retrieving memory for task: {task_context[:50]}...")

        features = await self._extract_task_features(task_context)

        tasks = []
        tasks.append(self.user_agent.get(user_id))

        if features["requires_knowledge"]:
            tasks.append(
                self.knowledge_agent.search(
                    query=task_context, domain=features["domain"], top_k=5
                )
            )
        if features["is_complex"]:
            tasks.append(
                self.experience_agent.find_similar_tasks(
                    task_context=task_context,
                    task_type=features["task_type"],
                    min_success_rate=0.7,
                    limit=3,
                )
            )
        if features["has_history"]:
            if task_id:
                tasks.append(self.task_agent.get_task_progress(task_id))
            else:
                tasks.append(
                    self.task_agent.get_recent_tasks(
                        user_id=user_id, task_type=features["task_type"], limit=5
                    )
                )
        if features.get("requires_research"):
            tasks.append(
                self.research_agent.search_papers(
                    query=task_context,
                    domain=features.get("research_domain"),
                    top_k=5,
                )
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        retrieved = {}
        all_keys = ["user", "knowledge", "experience", "task_progress", "task_history"]
        if features.get("requires_research"):
            all_keys.append("research")
        for key, result in zip(all_keys, results):
            if not isinstance(result, Exception) and result is not None:
                retrieved[key] = result

        scored = await self._compute_importance(retrieved, task_context, user_id)
        top_memories = sorted(scored, key=lambda x: x.importance, reverse=True)[:8]

        return {
            "working_memory": top_memories,
            "raw_memory_sources": retrieved,
            "task_features": features,
            "feedback_request": True,
            "retrieved_memories": top_memories,
        }

    async def _compute_importance(
        self, retrieved: Dict[str, Any], query: str, user_id: str
    ) -> List[MemoryRecord]:
        scored = []
        current_weights = self.rl_optimizer.get_current_weights()

        for source, memories in retrieved.items():
            if source == "user":
                user_mem = memories
                score = 0.8
                if user_mem.get("preferences", {}).get("response_style") == "concise":
                    score += 0.2 * current_weights["explicit_feedback"]
                scored.append(
                    MemoryRecord(
                        source=source,
                        content=f"User preferences: {json.dumps(user_mem.get('preferences', {}), ensure_ascii=False)}",
                        importance=round(score, 3),
                        metadata=user_mem,
                    )
                )
                habits = user_mem.get("habits", {})
                if habits:
                    scored.append(
                        MemoryRecord(
                            source=source,
                            content=f"User habits: {json.dumps(habits, ensure_ascii=False)}",
                            importance=round(score * 0.8, 3),
                            metadata=habits,
                        )
                    )

            elif source == "knowledge":
                for mem in memories:
                    relevance = mem["relevance"]
                    recency = 1.0
                    if "last_updated" in mem["metadata"]:
                        age = (
                            datetime.utcnow()
                            - datetime.fromisoformat(mem["metadata"]["last_updated"])
                        ).days
                        recency = max(0, 1 - age / 30)
                    trust = mem["metadata"].get("trust_score", 0.5)
                    score = (
                        relevance * current_weights["relevance"]
                        + recency * current_weights["recency"]
                        + trust * current_weights["trust_score"]
                    )
                    scored.append(
                        MemoryRecord(
                            source=source,
                            content=mem["content"],
                            importance=round(score, 3),
                            metadata=mem,
                        )
                    )

            elif source == "experience":
                for mem in memories:
                    relevance = 0.6
                    recency = 1.0
                    frequency = mem["frequency"]
                    score = (
                        relevance * current_weights["relevance"]
                        + frequency * current_weights["frequency"]
                        + 0.5 * current_weights["recency"]
                    )
                    scored.append(
                        MemoryRecord(
                            source=source,
                            content=mem["summary"],
                            importance=round(score, 3),
                            metadata=mem,
                        )
                    )

            elif source == "task_progress":
                score = 0.9
                scored.append(
                    MemoryRecord(
                        source=source,
                        content=f"Task progress: {json.dumps(memories, ensure_ascii=False)}",
                        importance=round(score, 3),
                        metadata=memories,
                    )
                )

            elif source == "task_history":
                for mem in memories:
                    score = 0.6
                    scored.append(
                        MemoryRecord(
                            source=source,
                            content=f"Previous task: {mem['title']} ({mem['status']})",
                            importance=round(score, 3),
                            metadata=mem,
                        )
                    )

            elif source == "research":
                for mem in memories:
                    score = (
                        mem["relevance"] * current_weights["relevance"]
                        + mem["importance_score"] * 0.3
                    )
                    key_points_str = "; ".join(mem.get("key_points", [])[:3])
                    scored.append(
                        MemoryRecord(
                            source=source,
                            content=f"[{mem.get('domain','general')}] {mem['title']}: {key_points_str}",
                            importance=round(score, 3),
                            metadata=mem,
                        )
                    )

        return scored

    async def store(
        self,
        user_id: str,
        task_id: str,
        context: List[Dict],
        task_status: str,
        success: bool = False,
        experience_summary: str = None,
    ):
        for msg in context:
            await self.context_agent.add_message(msg)
        await self.task_agent.create_task(
            user_id=user_id,
            task_id=task_id,
            title="自动任务",
            steps=[{"step": "初始化", "status": task_status}],
        )
        await self._infer_user_preferences(context, user_id)

        if self._persistence_enabled:
            user_data = await self.user_agent.get(user_id)
            await self.pg.save_user(user_id, user_data)
            await self.pg.save_task(
                user_id, task_id, "自动任务", task_status,
                steps=[{"step": "初始化", "status": task_status}],
            )

        if success or experience_summary:
            steps_from_context = [
                m["content"] for m in context if m["role"] != "system"
            ]
            await self.experience_agent.store_experience(
                task_id=task_id,
                success=success,
                steps=steps_from_context,
                summary=experience_summary or "系统自动生成的经验总结",
            )
            if self._persistence_enabled:
                await self.pg.save_experience(
                    user_id, "default_task", success, steps_from_context,
                    experience_summary or "系统自动生成的经验总结",
                )

    async def _infer_user_preferences(self, context: List[Dict], user_id: str):
        concise_count = sum(
            1 for msg in context if "简短" in msg["content"] or "简洁" in msg["content"]
        )
        if concise_count >= 2:
            await self.user_agent.update(
                user_id, "response_style", "concise", source="implicit"
            )

        # 新增：代码风格识别
        if any("type hint" in msg["content"] for msg in context) or any(
            "Optional[str]" in msg["content"] for msg in context
        ):
            await self.user_agent.update(
                user_id, "code_style", "detailed", source="implicit"
            )
        elif any("简洁" in msg["content"] for msg in context) or any(
            "不要注释" in msg["content"] for msg in context
        ):
            await self.user_agent.update(
                user_id, "code_style", "concise", source="implicit"
            )

    async def record_feedback(
        self, user_id: str, task_id: str, feedback: str, retrieved_memories: List[Dict]
    ):
        if feedback not in ["positive", "negative"]:
            raise ValueError("feedback must be 'positive' or 'negative'")
        from learning.rl_weight_optimizer import FeedbackRecord

        feedback_record = FeedbackRecord(
            user_id=user_id,
            task_id=task_id,
            retrieved_memories=retrieved_memories,
            user_feedback=feedback,
        )
        self.rl_optimizer.add_feedback(feedback_record)
        logger.info(f"User {user_id} gave {feedback} feedback on task {task_id}")

    async def sync_to_code_project(self, project_root: str, user_id: str):
        """
        将关键记忆写入项目根目录下的 .echomind/ 文件，供 Claude Code 读取
        """
        import os
        import json
        from pathlib import Path

        echomind_dir = Path(project_root) / ".echomind"
        echomind_dir.mkdir(exist_ok=True)

        user_mem = await self.user_agent.get(user_id)
        exp_mem = await self.experience_agent.find_similar_tasks(
            task_context=f"代码风格偏好: {user_mem.get('preferences', {}).get('code_style', 'standard')}",
            task_type="code_review",
            min_success_rate=0.6,
        )

        config = {
            "user_preferences": user_mem.get("preferences", {}),
            "user_habits": user_mem.get("habits", {}),
            "recent_code_experience": exp_mem[:3],
            "updated_at": datetime.utcnow().isoformat(),
        }

        (echomind_dir / "context.json").write_text(
            json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        summary = "=== EchoMind 记忆摘要 ===\n"
        if user_mem.get("preferences", {}).get("code_style") == "concise":
            summary += "▸ 你的代码风格偏好：简洁、无注释、函数短小\n"
        elif user_mem.get("preferences", {}).get("code_style") == "detailed":
            summary += "▸ 你的代码风格偏好：详尽注释、文档优先、模块化\n"

        for exp in exp_mem[:2]:
            summary += f"\n▸ 你曾成功修复：{exp['summary']}\n"

        research_papers = list(self.research_agent.papers.values())[:3]
        for rp in research_papers:
            summary += f"\n▸ 研究论文：{rp.title}（{rp.domain}）\n"

        (echomind_dir / "README.md").write_text(summary, encoding="utf-8")

        logger.info(f"✅ Synced EchoMind memories to {echomind_dir}")

    async def get_context(self) -> List[Dict]:
        return await self.context_agent.get_context()

    async def clear_context(self):
        await self.context_agent.clear()
