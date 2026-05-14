# EchoMind Memory — Hermes MemoryProvider 适配器
# 实现 Hermes 的 MemoryProvider 接口，提供 100% 自动化的记忆存取
#
# 安装：复制到 ~/.hermes/plugins/echomind-memory/
# 激活：hermes config set memory.provider echomind

import json
import logging
import sys
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

# 确保 core 模块可导入
_skill_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_dir = os.path.dirname(_skill_dir)
if _pkg_dir not in sys.path:
    sys.path.insert(0, _pkg_dir)

from core.memory_agent import MainMemoryAgent

logger = logging.getLogger("EchomindProvider")

PLATFORM = "hermes"


class EchomindMemoryProvider:
    """EchoMind Memory Provider — 与 Hermes Agent Loop 深度集成
    
    自动调用时序（由 Hermes run_agent.py 负责）：
    - 每轮前: prefetch(query, session_id) → 检索记忆，注入 system prompt
    - 每轮后: sync_turn(user, assistant, session_id) → 存储本轮对话
    - 会话结束: shutdown() → 持久化 + 清理
    
    也暴露 memory_search/memory_retrieve 工具，LLM 可显式调用。
    """

    name = "echomind"

    def __init__(self):
        self._agent: Optional[MainMemoryAgent] = None
        self._session_id: str = ""
        self._user_id: str = ""
        self._turn_count: int = 0
        self._context_buffer: List[Dict] = []

    # ═══════════════════════════════════════════════════
    # 生命周期
    # ═══════════════════════════════════════════════════

    def is_available(self) -> bool:
        """检查是否可用（不需要网络，本地 SQLite）"""
        return True

    def initialize(self, session_id: str, **kwargs):
        """Hermes 启动时调用，连接 SQLite + 加载历史记忆"""
        self._session_id = session_id
        self._user_id = kwargs.get("user_id", session_id)
        self._turn_count = 0
        self._context_buffer = []

        self._agent = MainMemoryAgent()
        self._agent.enable_persistence()
        
        logger.info(
            f"EchoMind Memory initialized: session={session_id}, "
            f"user={self._user_id}, platform={PLATFORM}"
        )

    def shutdown(self):
        """Hermes 退出时调用"""
        if self._agent:
            self._agent.disable_persistence()
        logger.info("EchoMind Memory shutdown")

    # ═══════════════════════════════════════════════════
    # 自动调用的核心方法（由 agent_loop 驱动，100% 可靠）
    # ═══════════════════════════════════════════════════

    def system_prompt_block(self) -> str:
        """注入到 system prompt 的静态文本"""
        return (
            "[EchoMind Memory]\n"
            "长期记忆系统已激活。你的对话会自动被记录和检索。\n"
            "如需显式搜索：使用 memory_search(query) 查找相关记忆。\n"
            "如需查看用户档案：使用 memory_retrieve() 获取偏好和历史。\n"
        )

    def prefetch(self, query: str, session_id: str) -> str:
        """每轮对话前自动调用 — 检索相关记忆注入上下文
        
        Returns:
            格式化的记忆文本，注入到当前对话的 messages 中
        """
        if not self._agent:
            return ""

        try:
            result = self._agent.retrieve_for_task(
                task_context=query,
                user_id=self._user_id,
                task_id=session_id,
                platform=PLATFORM,
            )
            return self._format_prefetch_context(result)
        except Exception as e:
            logger.error(f"prefetch error: {e}")
            return ""

    def sync_turn(self, user_content: str, assistant_content: str, session_id: str):
        """每轮对话后自动调用 — 存储本轮对话到 SQLite"""
        if not self._agent:
            return

        self._turn_count += 1
        self._session_id = session_id

        # 构建上下文消息列表
        messages = []
        if self._context_buffer:
            messages.extend(self._context_buffer)
            self._context_buffer = []
        messages.extend([
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": assistant_content},
        ])

        try:
            self._agent.store(
                user_id=self._user_id,
                task_id=f"{session_id}:turn{self._turn_count}",
                context=messages,
                task_status="completed",
                success=True,
                platform=PLATFORM,
            )
            logger.debug(f"sync_turn: turn {self._turn_count} stored")
        except Exception as e:
            logger.error(f"sync_turn error: {e}")
            # 失败时缓存到 buffer 下次重试
            self._context_buffer = messages[-6:]  # 保留最近 6 条

    # ═══════════════════════════════════════════════════
    # LLM 工具定义（显式调用，补充自动存取）
    # ═══════════════════════════════════════════════════

    def get_tool_schemas(self) -> List[Dict]:
        """暴露给 LLM 的工具定义"""
        return [
            {
                "name": "memory_search",
                "description": "搜索长期记忆中的相关内容。用于查找之前讨论过的话题、决策或偏好。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "搜索关键词或问句，如 'Python 爬虫'、'上周讨论的架构方案'",
                        }
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "memory_retrieve",
                "description": "获取当前用户的完整记忆档案，包括偏好、习惯和最近活动。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "detail_level": {
                            "type": "string",
                            "enum": ["brief", "full"],
                            "default": "brief",
                            "description": "明细程度：brief=摘要  full=完整记忆",
                        }
                    },
                },
            },
        ]

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any]) -> str:
        """处理 LLM 显式调用的工具"""
        if not self._agent:
            return "EchoMind 未初始化"

        try:
            if tool_name == "memory_search":
                return self._search(args.get("query", ""))
            elif tool_name == "memory_retrieve":
                return self._retrieve(args.get("detail_level", "brief"))
            else:
                return f"未知工具: {tool_name}"
        except Exception as e:
            logger.error(f"handle_tool_call error: {e}")
            return f"记忆操作失败: {str(e)}"

    # ═══════════════════════════════════════════════════
    # 可选钩子
    # ═══════════════════════════════════════════════════

    def on_turn_start(self, turn_number: int, message: str, **kwargs):
        """每轮开始时的钩子（可用于预加载）"""
        self._turn_count = turn_number

    def on_session_end(self, messages: List[Dict]):
        """会话结束时的钩子"""
        if self._agent and messages:
            try:
                self._agent.store(
                    user_id=self._user_id,
                    task_id=f"{self._session_id}:summary",
                    context=messages[-10:],  # 最近 10 轮
                    task_status="session_end",
                    success=True,
                    platform=PLATFORM,
                )
                logger.info("on_session_end: session summary stored")
            except Exception as e:
                logger.error(f"on_session_end error: {e}")

    def on_memory_write(self, action: str, target: str, content: str, metadata: Optional[Dict] = None):
        """镜像 Hermes 内置记忆的写入操作"""
        if not self._agent:
            return
        mirror = [
            {"role": "system", "content": f"[Memory {action}] target={target}"},
            {"role": "assistant", "content": content},
        ]
        try:
            self._agent.store(
                user_id=self._user_id,
                task_id=f"{self._session_id}:memory:{action}",
                context=mirror,
                task_status="memory_mirror",
                success=True,
                platform=PLATFORM,
            )
        except Exception:
            pass

    # ═══════════════════════════════════════════════════
    # 内部方法
    # ═══════════════════════════════════════════════════

    def _search(self, query: str) -> str:
        """执行记忆搜索"""
        if not query:
            return "请提供搜索关键词"
        result = self._agent.retrieve_for_task(
            task_context=query,
            user_id=self._user_id,
            platform=PLATFORM,
        )
        return self._format_search_result(result)

    def _retrieve(self, detail: str = "brief") -> str:
        """获取用户记忆档案"""
        user_data = self._agent.user_agent.get(self._user_id, platform=PLATFORM)
        if detail == "brief":
            prefs = user_data.get("preferences", {})
            if not prefs:
                return "暂无用户偏好记录"
            lines = [f"- {k}: {v}" for k, v in list(prefs.items())[:8]]
            return "用户偏好：\n" + "\n".join(lines) if lines else "暂无用户偏好记录"
        else:
            return json.dumps(user_data, indent=2, ensure_ascii=False, default=str)

    def _format_prefetch_context(self, result: Dict) -> str:
        """将检索结果格式化为注入上下文"""
        memories = result.get("retrieved_memories", [])
        if not memories:
            return ""

        lines = ["[EchoMind — 相关记忆]"]
        for mem in memories[:5]:
            source_label = mem.source.replace("_", " ").title()
            lines.append(f"[{source_label}] {mem.content[:200]}")
        
        # 附加用户偏好
        user_data = result.get("user", {})
        prefs = user_data.get("preferences", {})
        if prefs:
            pref_items = ", ".join(f"{k}={v}" for k, v in list(prefs.items())[:5])
            lines.append(f"[User Prefs] {pref_items}")

        return "\n".join(lines)

    def _format_search_result(self, result: Dict) -> str:
        """将检索结果格式化为 LLM 友好的文本"""
        memories = result.get("retrieved_memories", [])
        if not memories:
            return "未找到相关记忆"

        lines = ["找到以下相关记忆："]
        for i, mem in enumerate(memories[:8], 1):
            lines.append(f"{i}. [{mem.source}] {mem.content[:150]}")
        return "\n".join(lines)


# Hermes plugin 注册入口
# Hermes 会通过 importlib 加载此模块并调用 register()
def register(ctx):
    provider = EchomindMemoryProvider()
    ctx.register_memory_provider(provider)
    logger.info("EchoMind Memory Provider registered for Hermes")