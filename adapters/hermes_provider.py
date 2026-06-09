# EchoMind Memory — Hermes MemoryProvider Adapter
# implement Hermes v0.13.0+  MemoryProvider interface (v0.16.0 rewound param), providing 100% automated memory access
#
# Install: copy to ~/.hermes/plugins/echomind-memory/
# Activate: hermes config set memory.provider echomind

import json
import logging
import sys
import os
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests  # Hermes bundled, zero new dependencies

# Safe import MemoryProvider ABC (supports packaged + source Hermes)
try:
    from agent.memory_provider import MemoryProvider
except ImportError:
    from abc import ABC, abstractmethod

    class MemoryProvider(ABC):
        """Minimal MemoryProvider fallback for when Hermes agent module is unavailable."""
        name: str = ""

        @abstractmethod
        def is_available(self) -> bool: ...
        @abstractmethod
        def initialize(self, session_id: str, **kwargs): ...
        @abstractmethod
        def get_tool_schemas(self): ...

# Ensure core module is importable
_skill_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_dir = os.path.dirname(_skill_dir)
if _pkg_dir not in sys.path:
    sys.path.insert(0, _pkg_dir)

from core.memory_agent import MainMemoryAgent

logger = logging.getLogger("EchomindProvider")

PLATFORM = "hermes"


class EchomindMemoryProvider(MemoryProvider):
    """EchoMind Memory Provider — Hermes Agent loop deep integration
    
    Automatic invocation sequence (managed by Hermes run_agent.py):
    - before each turn: prefetch(query, session_id) → retrieve memory, inject system prompt
    - after each turn: sync_turn(user, assistant, session_id) → store current-turn conversation
    - after each turn: queue_prefetch(query, session_id) → queue for next-turn retrieval
    - session switch: on_session_switch(new_sid, ...) → Update session state
    - before compression: on_pre_compress(messages) → extract memories about to be compressed
    - session end: shutdown() → Persist + cleanup
    
    also exposes memory_search/memory_retrieve tools, LLM can call explicitly.
    """

    name = "echomind"

    def __init__(self):
        self._agent: Optional[MainMemoryAgent] = None
        self._session_id: str = ""
        self._user_id: str = ""
        self._profile: str = "default"
        self._turn_count: int = 0
        self._context_buffer: List[Dict] = []
        self._skip_writes: bool = False  # non-primary context Skip write
        self._project_id: str = "default"
        self._session_title: str = ""

    # ═══════════════════════════════════════════════════
    # Lifecycle
    # ═══════════════════════════════════════════════════

    def is_available(self) -> bool:
        """Check if available（no network required, local SQLite）"""
        return True

    def _derive_profile(self, hermes_home: str) -> str:
        """Extract profile name from hermes_home path, cross-platform compatible.

        Strategy (by priority):
        1. pathlib.Path.parts matches "profiles" segment (Linux/WSL/macOS)
        2. String match "/profiles/" (Unix path string)
        3. String match "\\profiles\\" or "\\profiles/" (Windows path string)
        4. Fallback "default"

        Supports:
        - Linux: /home/user/.hermes/profiles/weixin/plugins/echomind → weixin
        - Windows: C:\\Users\\user\\.hermes\\profiles\\weixin\\plugins\\echomind → weixin
        - WSL: /mnt/c/Users/user/.hermes/profiles/weixin/plugins/echomind → weixin
        - Default/no profile: → default
        """
        if not hermes_home:
            return "default"

        # Strategy 1: pathlib path parts match (Unix/WSL path)
        try:
            hermes_path = Path(hermes_home).resolve()
            parts = hermes_path.parts
            for i, part in enumerate(parts):
                if part == "profiles" and i + 1 < len(parts):
                    return parts[i + 1]
        except (IndexError, AttributeError, ValueError):
            pass

        # Strategy 2: Unix-style /profiles/ string match
        if "/profiles/" in hermes_home:
            return hermes_home.split("/profiles/")[-1].split("/")[0]

        # Strategy 3: Windows-style \\profiles\\ string match
        for sep in ('\\profiles\\', '\\profiles/'):
            if sep in hermes_home:
                return hermes_home.split(sep)[-1].split("\\")[0].split("/")[0]

        return "default"

    def initialize(self, session_id: str, **kwargs):
        """Hermes called on startup, connects SQLite + Load history on startup

        kwargs may contain: hermes_home, platform, agent_context, user_id etc.
        agent_context used to distinguish primary/subagent/cron/flush scenarios.

        Hermes v1.1.6+: auto-derive profile from hermes_home path.
        """
        # Non-primary context (subagent/cron/flush) — do not write to user memory
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
        self._profile = self._derive_profile(kwargs.get("hermes_home", ""))
        self._project_id = kwargs.get("project", "default")
        self._turn_count = 0
        self._context_buffer = []

        self._agent = MainMemoryAgent()
        self._agent.enable_persistence()

        logger.info(
            f"EchoMind Memory initialized: session={session_id}, "
            f"user={self._user_id}, profile={self._profile}, "
            f"project={self._project_id}, platform={PLATFORM}"
        )

    def shutdown(self):
        """Hermes called on exit"""
        if self._agent:
            self._agent.disable_persistence()
        logger.info("EchoMind Memory shutdown")

    def get_config_schema(self):
        """Hermes v0.13.0+ config wizard schema"""
        return []

    def save_config(self, values, hermes_home: str) -> None:
        """Hermes v0.13.0+ save config from setup wizard"""
        pass

    # ═══════════════════════════════════════════════════
    # Core methods called automatically (agent_loop driven, 100% reliable)
    # ═══════════════════════════════════════════════════

    def system_prompt_block(self) -> str:
        """injected into system prompt static text of"""
        return (
            "[EchoMind Memory]\n"
            "Long-term memory system activated. Your conversations will be automatically recorded and retrieved.\n"
            "For explicit search: use memory_search(query) to find relevant memories.\n"
            "To view user profile: use memory_retrieve() to get preferences and history.\n"
        )

    def prefetch(self, query: str, session_id: str) -> str:
        """Automatically called before each conversation turn — Retrieve relevant memories and inject into context
        
        Returns:
            Formatted memory text, injected into the current conversation's messages
        """
        if self._skip_writes or not self._agent:
            return ""

        try:
            result = self._agent.retrieve_for_task(
                task_context=query,
                user_id=self._user_id,
                task_id=session_id,
                platform=PLATFORM,
                project=self._project_id,
                session_id=self._session_id,
                profile=self._profile,
            )
            return self._format_prefetch_context(result)
        except Exception as e:
            logger.error(f"prefetch error: {e}")
            return ""

    def queue_prefetch(self, query: str, session_id: str = "") -> None:
        """Queue background prefetch -- Hermes v0.13.0+ new interface.
        
        echomind prefetch is synchronous (local SQLite), no queue needed,
        but must exist for compatibility with MemoryProvider ABC.
        """
        pass

    def sync_turn(self, user_content: str, assistant_content: str, session_id: str):
        """Automatically called after each conversation turn — store current turn to SQLite"""
        if self._skip_writes or not self._agent:
            return

        self._turn_count += 1
        self._session_id = session_id

        # Build context message list
        messages = []
        if self._context_buffer:
            messages.extend(self._context_buffer)
            self._context_buffer = []
        messages.extend([
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": assistant_content},
        ])

        try:
            ok = self._agent.store(
                user_id=self._user_id,
                task_id=f"{session_id}:turn{self._turn_count}",
                context=messages,
                task_status="completed",
                success=True,
                platform=PLATFORM,
                project=self._project_id,
                session_id=session_id,
                profile=self._profile,
            )
            if ok:
                logger.debug(f"sync_turn: turn {self._turn_count} stored")
            else:
                logger.warning(f"sync_turn: turn {self._turn_count} store failed")
        except Exception as e:
            logger.error(f"sync_turn error: {e}")
            # cache to on failure buffer retry on next
            self._context_buffer = messages[-20:]  # keep recent 20 messages

    # ═══════════════════════════════════════════════════
    # LLM Tool definitions（Explicit invocation, supplementing auto-access）
    # ═══════════════════════════════════════════════════

    def get_tool_schemas(self) -> List[Dict]:
        """exposed to LLM tool definitions for"""
        return [
            {
                "name": "memory_search",
                "description": "Search long-term memory for relevant content. Used to find previously discussed topics, decisions, or preferences.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search keywords or questions, e.g. 'Python web crawler'、'last week's architecture discussion'",
                        }
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "memory_retrieve",
                "description": "Get the current user's complete memory profile, including preferences, habits, and recent activity.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "detail_level": {
                            "type": "string",
                            "enum": ["brief", "full"],
                            "default": "brief",
                            "description": "Detail level: brief=summary  full=full memory",
                        }
                    },
                },
            },
        ]

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:
        """Handle LLM Tools called explicitly.
        
        Hermes ABC Requires returning JSON string.
        """
        if not self._agent:
            return json.dumps({"error": "EchoMind Not initialized"}, ensure_ascii=False)

        try:
            if tool_name == "memory_search":
                result = self._search(args.get("query", ""))
                return json.dumps({"result": result}, ensure_ascii=False)
            elif tool_name == "memory_retrieve":
                result = self._retrieve(args.get("detail_level", "brief"))
                return json.dumps({"result": result}, ensure_ascii=False)
            else:
                return json.dumps({"error": f"Unknown tool: {tool_name}"}, ensure_ascii=False)
        except Exception as e:
            logger.error(f"handle_tool_call error: {e}")
            return json.dumps({"error": f"Memory operation failed: {str(e)}"}, ensure_ascii=False)

    # ═══════════════════════════════════════════════════
    # Optional hooks（Hermes v0.13.0+ standard）
    # ═══════════════════════════════════════════════════

    def on_turn_start(self, turn_number: int, message: str, **kwargs):
        """Hook at the start of each turn（Can be used for preloading）"""
        self._turn_count = turn_number

    def on_session_end(self, messages: List[Dict]):
        """Hook at the end of a session.
        
        Store session summary to long-term memory.
        """
        if self._skip_writes or not self._agent or not messages:
            return
        try:
            # Save full transcript for session search
            if self._agent and getattr(self._agent, '_persistence_enabled', False):
                try:
                    self._agent.db.save_transcript(
                        self._session_id, self._user_id,
                        messages, project=self._project_id,
                        profile=self._profile)
                except Exception as ex:
                    logger.error(f"transcript save error: {ex}")
            # Filter to standard role/content messages only
            clean_messages = [
                {"role": m["role"], "content": m["content"]}
                for m in messages[-10:]
                if isinstance(m, dict) and "role" in m and "content" in m
            ]
            if not clean_messages:
                return
            ok = self._agent.store(
                user_id=self._user_id,
                task_id=f"{self._session_id}:summary",
                context=clean_messages,
                task_status="session_end",
                success=True,
                platform=PLATFORM,
                project=self._project_id,
                session_id=self._session_id,
                profile=self._profile,
            )
            if ok:
                logger.info("on_session_end: session summary stored")
            else:
                logger.warning("on_session_end: store failed")
        except Exception as e:
            logger.error(f"on_session_end error: {e}")

        # v1.1.0: Check if reflection should be triggered
        self._trigger_reflection_if_needed()

    def on_session_switch(
        self,
        new_session_id: str,
        parent_session_id: str = "",
        reset: bool = False,
        rewound: bool = False,  # Hermes v0.16.0+: True when /undo N truncates history
        **kwargs,
    ):
        """Called on session switch（Hermes v0.13.0+ New）。

        /resume, /branch, /reset, context Triggered by operations like compression.
        Update internal session_id state, ensuring subsequent writes use the correct session.

        Hermes v0.16.0+: rewound=True when /undo N truncates conversation history
        without changing session_id. Provider should invalidate caches.
        """
        if reset:
            # /new, /reset: Clear buffer
            self._context_buffer = []
            self._turn_count = 0

        if rewound:
            # /undo N: Clear context cache so subsequent turns don't use stale state
            if self._agent:
                self._agent.clear_context()
            logger.info(
                "on_session_switch: rewound=True — context cache cleared for %s",
                new_session_id,
            )

        self._session_id = new_session_id
        logger.info(
            "on_session_switch: new=%s parent=%s reset=%s rewound=%s",
            new_session_id, parent_session_id, reset, rewound,
        )

    def on_pre_compress(self, messages: List[Dict[str, Any]]) -> str:
        """Called before context compression（Hermes v0.13.0+ New）。
        
        Extract retainable memories from messages before they are discarded.
        Return empty string to indicate no additional compression hints（Memory auto-stored）。
        """
        if self._skip_writes or not self._agent or not messages:
            return ""
        try:
            # Store messages about to be compressed into long-term memory
            ok = self._agent.store(
                user_id=self._user_id,
                task_id=f"{self._session_id}:compress",
                context=messages[-20:],
                task_status="compressed",
                project=self._project_id,
                session_id=self._session_id,
                success=True,
                platform=PLATFORM,
                profile=self._profile,
            )
            if ok:
                logger.debug("on_pre_compress: %d messages preserved", min(20, len(messages)))
            else:
                logger.warning("on_pre_compress: store failed")
        except Exception as e:
            logger.error(f"on_pre_compress error: {e}")
        return ""

    def on_delegation(self, task: str, result: str, child_session_id: str = "", **kwargs):
        """Sub-agent completed callback (Hermes v0.13.0+).
        
        Store child agent task and result as experience.
        """
        if self._skip_writes or not self._agent:
            return
        try:
            ok = self._agent.store(
                user_id=self._user_id,
                task_id=f"{self._session_id}:delegation:{child_session_id}",
                context=[
                    {"role": "user", "content": f"[Delegation Task]\n{task}"},
                    {"role": "assistant", "content": f"[Delegation Result]\n{result[:2000]}"},
                ],
                task_status="delegated",
                success=True,
                platform=PLATFORM,
                project=self._project_id,
                session_id=self._session_id,
                profile=self._profile,
            )
            logger.debug("on_delegation: child=%s stored (ok=%s)", child_session_id, ok)
        except Exception as e:
            logger.error(f"on_delegation error: {e}")

    def _trigger_reflection_if_needed(self):
        """If store Count reaches threshold, auto-invoke LLM perform reflection"""
        if not self._agent:
            return
        from core.config_manager import get_config_manager
        cfg = get_config_manager().get_section("reflection")
        batch_size = cfg.get("batch_size", 8)
        if isinstance(batch_size, (list, tuple)):
            batch_size = int(random.uniform(batch_size[0], batch_size[1]))
        min_records = cfg.get("min_records", 6)
        pending = getattr(self._agent, '_pending_reflection', False)
        if not pending:
            return
        records = self._agent.get_recent_episodic(self._user_id, count=batch_size)
        if len(records) < min_records:
            return
        logger.info(f"Reflection triggered: {len(records)} records")
        try:
            result = self._agent.reflective.reflect_with_llm(
                records, self._user_id, PLATFORM, _hermes_llm_fn,
            )
            if result:
                logger.info(
                    f"Reflection done: {len(result.key_insights)} insights "
                    f"(confidence={result.confidence:.2f})"
                )
        except Exception as e:
            logger.warning(f"Reflection failed: {e}")
        finally:
            self._agent.clear_pending_reflection()

    def on_memory_write(self, action: str, target: str, content: str, metadata: Optional[Dict] = None):
        """Mirror Hermes built-in memory write operations"""
        if self._skip_writes or not self._agent:
            return
        mirror = [
            {"role": "system", "content": f"[Memory {action}] target={target}"},
            {"role": "assistant", "content": content},
        ]
        try:
            ok = self._agent.store(
                user_id=self._user_id,
                task_id=f"{self._session_id}:memory:{action}",
                context=mirror,
                task_status="memory_mirror",
                success=True,
                platform=PLATFORM,
                project=self._project_id,
                session_id=self._session_id,
                profile=self._profile,
            )
            logger.info(
                "EchoMind: mirrored memory %s target=%s content_len=%d (ok=%s)",
                action, target, len(content), ok,
            )
        except Exception as e:
            logger.error(
                "EchoMind: on_memory_write failed action=%s target=%s: %s",
                action, target, e,
            )

    # ═══════════════════════════════════════════════════
    # Internal method
    # ═══════════════════════════════════════════════════

    def _search(self, query: str) -> str:
        """Execute memory search"""
        if not query:
            return "Please provide search keywords"
        result = self._agent.retrieve_for_task(
            task_context=query,
            user_id=self._user_id,
            platform=PLATFORM,
        )
        return self._format_search_result(result)

    def _retrieve(self, detail: str = "brief") -> str:
        """Get user memory profile"""
        user_data = self._agent.user_agent.get(self._user_id, platform=PLATFORM)
        if detail == "brief":
            prefs = user_data.get("preferences", {})
            if not prefs:
                return "No user preference records yet"
            lines = [f"- {k}: {v}" for k, v in list(prefs.items())[:8]]
            return "User preferences:\n" + "\n".join(lines) if lines else "No user preference records yet"
        else:
            return json.dumps(user_data, indent=2, ensure_ascii=False, default=str)

    def _format_prefetch_context(self, result: Dict) -> str:
        """Format retrieval results as context injection"""
        memories = result.get("retrieved_memories", [])
        if not memories:
            return ""

        lines = ["[EchoMind — Relevant memories]"]
        for mem in memories[:5]:
            source_label = mem.source.replace("_", " ").title()
            lines.append(f"[{source_label}] {mem.content[:200]}")
        
        # Append user preferences
        user_data = result.get("user", {})
        prefs = user_data.get("preferences", {})
        if prefs:
            pref_items = ", ".join(f"{k}={v}" for k, v in list(prefs.items())[:5])
            lines.append(f"[User Prefs] {pref_items}")

        return "\n".join(lines)

    def _format_search_result(self, result: Dict) -> str:
        """Format retrieval results as LLM friendly text"""
        memories = result.get("retrieved_memories", [])
        if not memories:
            return "No relevant memories found"

        lines = ["Found the following relevant memories:"]
        for i, mem in enumerate(memories[:8], 1):
            lines.append(f"{i}. [{mem.source}] {mem.content[:150]}")
        return "\n".join(lines)


# Hermes plugin Registration entry point
# Hermes will through importlib load this module and call register()
def register(ctx, **kwargs):
    provider = EchomindMemoryProvider()
    ctx.register_memory_provider(provider)
    logger.info("EchoMind Memory Provider registered for Hermes")


# v1.1.0: LLM function injection（passed UnifiedLLMClient Unified invocation, supports external API）
_llm_client = None


def _get_llm_client():
    global _llm_client
    if _llm_client is None:
        from core.llm_client import get_llm_client
        _llm_client = get_llm_client()
    return _llm_client


def _hermes_llm_fn(prompt: str) -> str:
    """passed UnifiedLLMClient calls LLM for reflection.

    Supports external API endpoints (OpenAI / vLLM / Ollama, etc.).
    """
    client = _get_llm_client()
    if client is None:
        return ""
    return client.chat(prompt)