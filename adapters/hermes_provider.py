# EchoMind Memory — Hermes MemoryProvider 适配器
# 实现 Hermes v0.13.0+ 的 MemoryProvider 接口，提供 100% 自动化的记忆存取
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
    - 每轮后: queue_prefetch(query, session_id) → 排队下轮检索
    - 会话切换: on_session_switch(new_sid, ...) → 更新 session 状态
    - 压缩前: on_pre_compress(messages) → 提取即将被压缩的记忆
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
        self._skip_writes: bool = False  # non-primary context 跳过写入

    # ═══════════════════════════════════════════════════
    # 生命周期
    # ═══════════════════════════════════════════════════

    def is_available(self) -> bool:
        """检查是否可用（不需要网络，本地 SQLite）"""
        return True

    def initialize(self, session_id: str, **kwargs):
        """Hermes 启动时调用，连接 SQLite + 加载历史记忆
        
        kwargs 可能包含: hermes_home, platform, agent_context, user_id 等。
        agent_context 用于区分 primary/subagent/cron/flush 场景。
        """
        # 非 primary context（subagent/cron/flush）不写入用户记忆
        agent_ctx = kwargs.get("agent_context", "primary")
        if agent_ctx != "primary":
            logger.info(
                "EchoMind: skipping initialize for non-primary context=%s session=%s",
                agent_ctx, session_id,
            )
            self._skip_writes = True
            self._session_id = session_id
            return

        self._skip_writes = False
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
        if self._skip_writes or not self._agent:
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

    def queue_prefetch(self, query: str, session_id: str = "") -> None:
        """排队后台预取——Hermes v0.13.0+ 新增接口。
        
        echomind 的 prefetch 是同步的（本地 SQLite），无需排队，
        但需要存在以兼容 MemoryProvider ABC。
        """
        pass

    def sync_turn(self, user_content: str, assistant_content: str, session_id: str):
        """每轮对话后自动调用 — 存储本轮对话到 SQLite"""
        if self._skip_writes or not self._agent:
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
        """处理 LLM 显式调用的工具。
        
        Hermes ABC 要求返回 JSON 字符串。
        """
        if not self._agent:
            return json.dumps({"error": "EchoMind 未初始化"}, ensure_ascii=False)

        try:
            if tool_name == "memory_search":
                result = self._search(args.get("query", ""))
                return json.dumps({"result": result}, ensure_ascii=False)
            elif tool_name == "memory_retrieve":
                result = self._retrieve(args.get("detail_level", "brief"))
                return json.dumps({"result": result}, ensure_ascii=False)
            else:
                return json.dumps({"error": f"未知工具: {tool_name}"}, ensure_ascii=False)
        except Exception as e:
            logger.error(f"handle_tool_call error: {e}")
            return json.dumps({"error": f"记忆操作失败: {str(e)}"}, ensure_ascii=False)

    # ═══════════════════════════════════════════════════
    # 可选钩子（Hermes v0.13.0+ 规范）
    # ═══════════════════════════════════════════════════

    def on_turn_start(self, turn_number: int, message: str, **kwargs):
        """每轮开始时的钩子（可用于预加载）"""
        self._turn_count = turn_number

    def on_session_end(self, messages: List[Dict]):
        """会话结束时的钩子。
        
        存储会话摘要到长期记忆。
        """
        if self._skip_writes or not self._agent or not messages:
            return
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

    def on_session_switch(
        self,
        new_session_id: str,
        parent_session_id: str = "",
        reset: bool = False,
        **kwargs,
    ):
        """会话切换时调用（Hermes v0.13.0+ 新增）。
        
        /resume, /branch, /reset, context 压缩等操作会触发。
        更新内部 session_id 状态，确保后续写入使用正确的 session。
        """
        if reset:
            # /new, /reset: 清空缓冲
            self._context_buffer = []
            self._turn_count = 0
        self._session_id = new_session_id
        logger.info(
            "on_session_switch: new=%s parent=%s reset=%s",
            new_session_id, parent_session_id, reset,
        )

    def on_pre_compress(self, messages: List[Dict[str, Any]]) -> str:
        """上下文压缩前调用（Hermes v0.13.0+ 新增）。
        
        在消息被丢弃前提取其中可保留的记忆。
        返回空字符串表示不贡献额外压缩提示（记忆已自动存储）。
        """
        if self._skip_writes or not self._agent or not messages:
            return ""
        try:
            # 将即将被压缩的消息存入长期记忆
            self._agent.store(
                user_id=self._user_id,
                task_id=f"{self._session_id}:compress",
                context=messages[-20:],
                task_status="compressed",
                success=True,
                platform=PLATFORM,
            )
            logger.debug("on_pre_compress: %d messages preserved", min(20, len(messages)))
        except Exception as e:
            logger.error(f"on_pre_compress error: {e}")
        return ""

    def on_delegation(self, task: str, result: str, child_session_id: str = "", **kwargs):
        """子 agent 完成时调用（Hermes v0.13.0+ 新增）。
        
        将子 agent 的任务和结果作为经验存储。
        """
        if self._skip_writes or not self._agent:
            return
        try:
            self._agent.store(
                user_id=self._user_id,
                task_id=f"{self._session_id}:delegation:{child_session_id}",
                context=[
                    {"role": "user", "content": f"[Delegation Task]\n{task}"},
                    {"role": "assistant", "content": f"[Delegation Result]\n{result[:2000]}"},
                ],
                task_status="delegated",
                success=True,
                platform=PLATFORM,
            )
            logger.debug("on_delegation: child=%s stored", child_session_id)
        except Exception as e:
            logger.error(f"on_delegation error: {e}")

    def on_memory_write(self, action: str, target: str, content: str, metadata: Optional[Dict] = None):
        """镜像 Hermes 内置记忆的写入操作"""
        if self._skip_writes or not self._agent:
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