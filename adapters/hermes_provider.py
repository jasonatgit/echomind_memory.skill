# EchoMind Memory — Hermes MemoryProvider Adapter
# Hermes Agent v0.17.0 MemoryProvider interface
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

# No ABC inheritance — Hermes discovers methods at runtime via getattr() / inspect.
# Compatible with Hermes v0.13.0+ without version-specific code.

# Ensure core module is importable
_skill_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_dir = os.path.dirname(_skill_dir)
if _pkg_dir not in sys.path:
    sys.path.insert(0, _pkg_dir)

from core.memory_agent import MainMemoryAgent

logger = logging.getLogger("EchomindProvider")

PLATFORM = "hermes"


class EchomindMemoryProvider:
    """EchoMind Memory Provider — Hermes Agent loop deep integration

    No ABC inheritance.  Hermes discovers available methods at runtime
    via getattr() and adapts keyword arguments via inspect.signature(),
    so a plain class without any framework base class works identically.

    Hermes v0.17.0 MemoryProvider protocol:
      name() -> str
      is_available() -> bool
      initialize(session_id, **kwargs)
      system_prompt_block() -> str
      prefetch(query, *, session_id) -> str
      queue_prefetch(query, *, session_id)
      sync_turn(user_content, assistant_content, *, session_id, messages)
      get_tool_schemas() -> list[dict]
      handle_tool_call(tool_name, args, **kwargs) -> str
      shutdown()
      on_turn_start(turn_number, message, **kwargs)
      on_session_end(messages)
      on_session_switch(new_session_id, *, parent_session_id, reset, rewound, **kwargs)
      on_pre_compress(messages) -> str
      on_delegation(task, result, *, child_session_id, **kwargs)
      on_memory_write(action, target, content, metadata)
      get_config_schema() -> list[dict]
      save_config(values, hermes_home)
      backup_paths() -> list[str]
      get_config_schema() -> list[dict]
      save_config(values, hermes_home)

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
        self._detected_lang: str = "en"  # auto-detected from user content
        self._agent_identity: str = ""   # Hermes v0.17.0: profile name
        self._agent_workspace: str = ""  # Hermes v0.17.0: workspace name

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
        for sep in ("\\profiles\\", "\\profiles/"):
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
                agent_ctx,
                session_id,
            )
            self._skip_writes = True
            self._session_id = session_id
            return

        self._skip_writes = False
        self._session_id = session_id
        self._user_id = kwargs.get("user_id", session_id)
        # R3 fix: Hermes passes the active profile (分身) name via
        # agent_identity (agent_init.py:1312 get_active_profile_name()).
        # Prefer it as the memory-scoping profile so each Hermes persona is
        # isolated; _derive_profile(hermes_home) only serves as a fallback for
        # hosts that do not thread agent_identity (e.g. older Hermes versions,
        # where the default profile lives directly under ~/.hermes with no
        # "profiles" path segment and _derive_profile would return "default").
        agent_identity = kwargs.get("agent_identity", "")
        derived_profile = self._derive_profile(kwargs.get("hermes_home", ""))
        self._profile = agent_identity or derived_profile or "default"
        self._agent_identity = agent_identity
        self._agent_workspace = kwargs.get("agent_workspace", "default")
        # R3 fix: prefer an explicit project kwarg (real project path) when the
        # host supplies one; only fall back to agent_workspace (host may hardcode
        # "hermes") or "default". This lets Hermes share memory with DSH/Zcode by
        # project instead of writing everything under a fixed "hermes" project.
        explicit_project = kwargs.get("project", "")
        if explicit_project and explicit_project != "default":
            self._project_id = explicit_project
        elif self._agent_workspace and self._agent_workspace != "default" and self._agent_workspace != "hermes":
            self._project_id = self._agent_workspace
        else:
            self._project_id = "default"
        self._turn_count = 0
        self._context_buffer = []

        self._agent = MainMemoryAgent()
        self._agent.enable_persistence()

        # Auto-sync LLM config from Hermes config.yaml
        # Inject as runtime overrides so user's explicit config takes priority
        self._sync_hermes_llm_config(**kwargs)

        logger.info(
            f"EchoMind Memory initialized: session={session_id}, "
            f"user={self._user_id}, profile={self._profile}, "
            f"project={self._project_id}, platform={PLATFORM}"
        )

    def shutdown(self):
        """Hermes called on exit"""
        if self._agent:
            pending = getattr(self._agent, "_pending_reflection", False)
            if pending:
                # C-M1/P14: scope to this session's profile and attribute the
                # reflection to the hermes platform.
                self._agent._trigger_auto_reflection(
                    self._user_id, profile=self._profile, platform=PLATFORM)
            # C-H1/P3: _trigger_auto_reflection spawns a daemon thread; wait for
            # it to finish before disable_persistence() closes the DB, or the
            # reflection is deterministically dropped (get_recent_episodic and
            # save_reflection are both gated on _persistence_enabled). Timeout
            # bounds the wait so a hung LLM call can't block exit forever.
            t = getattr(self._agent, "_reflection_thread", None)
            if t is not None and t.is_alive():
                t.join(timeout=30)
            self._agent.disable_persistence()
        logger.info("EchoMind Memory shutdown")

    def _sync_hermes_llm_config(self, **kwargs):
        """Read Hermes config.yaml and inject LLM settings as runtime overrides.

        Only syncs when EchoMind's own LLM endpoint is not explicitly configured
        (empty or set to the __HERMES_SYNCED__ marker).
        User's explicit config always takes priority.
        """
        try:
            from core.config_manager import get_config_manager
            cfg = get_config_manager()

            # Skip sync if user has explicitly configured an endpoint
            current_endpoint = cfg.get("llm", "endpoint", default="")
            if current_endpoint and current_endpoint != "__HERMES_SYNCED__":
                logger.debug("LLM auto-sync skipped: user-configured endpoint exists")
                return

            hermes_home = kwargs.get("hermes_home", "")
            if not hermes_home:
                import os
                hermes_home = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
            config_path = Path(hermes_home) / "config.yaml"
            if not config_path.exists():
                logger.debug("LLM auto-sync skipped: %s not found", config_path)
                return

            import yaml
            with open(config_path, encoding="utf-8") as f:
                hermes_conf = yaml.safe_load(f) or {}

            model_cfg = hermes_conf.get("model", {})
            if not isinstance(model_cfg, dict) or not model_cfg:
                logger.debug("LLM auto-sync skipped: no model section in Hermes config")
                return

            endpoint = model_cfg.get("endpoint") or model_cfg.get("base_url", "")
            api_key = model_cfg.get("api_key", "")
            model_name = model_cfg.get("model") or model_cfg.get("default_model", "")
            provider = model_cfg.get("provider", "openai_compatible")

            overrides = {"llm.provider": provider}
            if endpoint:
                overrides["llm.endpoint"] = endpoint
            if api_key:
                overrides["llm.api_key"] = api_key
            if model_name:
                overrides["llm.model"] = model_name

            for k, v in overrides.items():
                cfg.set_runtime(k, v)

            from core.llm_client import reload_llm_client
            reload_llm_client()
            logger.info("LLM config synced from Hermes: provider=%s", provider)
        except Exception as e:
            logger.debug("LLM config auto-sync skipped: %s", e)

    # ═══════════════════════════════════════════════════
    # Core methods called automatically (agent_loop driven, 100% reliable)
    # ═══════════════════════════════════════════════════

    def system_prompt_block(self) -> str:
        """injected into system prompt static text of"""
        from core.lang_utils import get_prompt

        base = get_prompt("hermes_sysprompt", self._detected_lang)
        # Append real-time memory system diagnostics (autoreflection upgrade: telemetry→reasoning)
        try:
            if self._agent and self._agent._persistence_enabled:
                stats = self._agent.db.get_memory_stats()
                cw = self._agent.rl_optimizer.get_current_weights()
                diag = "\n\n## Your Memory System (EchoMind v" + \
                    self._agent.reflective.get_engine_status().get("engine", "?") + ")\n"
                diag += "You have a persistent memory with 6 types across SQLite tables.\n"
                diag += "- Knowledge: {active}/{stale}/{archived} | Experience: {exp_active}\n".format(
                    active=stats.get("knowledge", {}).get("active", 0),
                    stale=stats.get("knowledge", {}).get("stale", 0),
                    archived=stats.get("knowledge", {}).get("archived", 0),
                    exp_active=stats.get("experience", {}).get("active", 0),
                )
                diag += "- RL weights: rel={:.2f} rec={:.2f} freq={:.2f}\n".format(
                    cw.get("relevance", 0.5), cw.get("recency", 0.5), cw.get("frequency", 0.5),
                )
                diag += "- Knowledge evolution: " + (
                    "active" if stats.get("knowledge", {}).get("active", 0) > 0 else "inactive") + "\n"
                base += diag
        except Exception:
            pass  # diagnostics are best-effort; never break the agent loop
        return base

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

    # ── Correction signal detection ──

    _CORRECTION_KEYWORDS_ZH = ["不对", "错了", "不是这样", "更正", "改一下"]
    _CORRECTION_KEYWORDS_ZH_WEAK = ["应该是", "不对的"]
    _CORRECTION_KEYWORDS_EN = ["mistake", "incorrect", "not correct"]
    _CORRECTION_KEYWORDS_EN_WEAK = ["wrong", "actually", "instead", "should be"]
    _NEGATION_CONTEXT = ["not", "no", "n't", "不要", "不能", "不是"]

    def _detect_correction(self, user_content: str) -> bool:
        """Detect if user is correcting the agent's response.

        Two-tier detection:
        - Strong keywords always trigger (e.g. "mistake", "不对")
        - Weak keywords only trigger with context (sentence-start or negation nearby)
        """
        if not user_content:
            return False
        lower = user_content.lower()
        # Tier 1: strong keywords (always trigger)
        for kw in self._CORRECTION_KEYWORDS_ZH:
            if kw in user_content:
                return True
        for kw in self._CORRECTION_KEYWORDS_EN:
            if kw in lower:
                return True
        # Tier 2: weak keywords (require contextual evidence)
        for kw in self._CORRECTION_KEYWORDS_ZH_WEAK:
            if kw in user_content:
                # Check if near a negation word
                idx = user_content.find(kw)
                window = user_content[max(0, idx - 20):idx + len(kw) + 20]
                if any(neg in window for neg in self._NEGATION_CONTEXT):
                    return True
        for kw in self._CORRECTION_KEYWORDS_EN_WEAK:
            if kw in lower:
                idx = lower.find(kw)
                # Trigger if at sentence start (first 50 chars) or near negation
                if idx < 50:
                    return True
                window = lower[max(0, idx - 30):idx + len(kw) + 30]
                if any(neg in window for neg in self._NEGATION_CONTEXT):
                    return True
        return False

    def sync_turn(self, user_content: str, assistant_content: str, *,
                  session_id: str = "", messages: Optional[List[Dict]] = None):
        """Automatically called after each conversation turn — store current turn to SQLite"""
        if self._skip_writes or not self._agent:
            return

        self._turn_count += 1
        if session_id:
            self._session_id = session_id

        # Detect language from user content for bilingual prompts
        if user_content:
            from core.lang_utils import detect_language

            self._detected_lang = detect_language(user_content)

        # Build context message list (use local var, don't shadow function parameter)
        ctx_messages = []
        if self._context_buffer:
            ctx_messages.extend(self._context_buffer)
            self._context_buffer = []
        ctx_messages.extend(
            [
                {"role": "user", "content": user_content},
                {"role": "assistant", "content": assistant_content},
            ]
        )

        # O-3: Detect user correction signals for immediate reflection
        correction = self._detect_correction(user_content)

        try:
            ok = self._agent.store(
                user_id=self._user_id,
                task_id=f"{session_id}:turn{self._turn_count}",
                context=ctx_messages,
                task_status="completed",
                success=True,
                platform=PLATFORM,
                project=self._project_id,
                session_id=session_id,
                profile=self._profile,
                correction=correction,
            )
            if ok:
                logger.debug(f"sync_turn: turn {self._turn_count} stored")
            else:
                logger.warning(f"sync_turn: turn {self._turn_count} store failed")
        except Exception as e:
            logger.error(f"sync_turn error: {e}")
            # cache to retry on next turn; guard against messages=None
            self._context_buffer = (messages or [])[-20:]  # keep recent 20 messages

    # ═══════════════════════════════════════════════════
    # LLM Tool definitions（Explicit invocation, supplementing auto-access）
    # ═══════════════════════════════════════════════════

    def get_tool_schemas(self) -> List[Dict]:
        """exposed to LLM tool definitions for"""
        from core.lang_utils import get_tool_descriptions

        td = get_tool_descriptions(self._detected_lang)
        return [
            {
                "name": "memory_search",
                "description": td.get(
                    "memory_search", "Search long-term memory for relevant content."
                ),
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
                "description": td.get(
                    "memory_retrieve", "Get the current user's complete memory profile."
                ),
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
                return json.dumps(
                    {"error": f"Unknown tool: {tool_name}"}, ensure_ascii=False
                )
        except Exception as e:
            logger.error(f"handle_tool_call error: {e}")
            return json.dumps(
                {"error": f"Memory operation failed: {str(e)}"}, ensure_ascii=False
            )

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
            if self._agent and getattr(self._agent, "_persistence_enabled", False):
                try:
                    self._agent.db.save_transcript(
                        self._session_id,
                        self._user_id,
                        messages,
                        project=self._project_id,
                        profile=self._profile,
                    )
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
                correction=any(self._detect_correction(m.get("content", "")) for m in clean_messages if m.get("role") == "user"),
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
        try:
            # Flush pending reflection before switching context
            self._trigger_reflection_if_needed()

            if reset:
                # /new, /reset: Clear buffer
                self._context_buffer = []
                self._turn_count = 0

            if rewound:
                # /undo N: Clear context cache and retry buffer
                self._context_buffer = []
                if self._agent:
                    self._agent.clear_context()
                logger.info(
                    "on_session_switch: rewound=True — context cache cleared for %s",
                    new_session_id,
                )

            self._session_id = new_session_id
            logger.info(
                "on_session_switch: new=%s parent=%s reset=%s rewound=%s",
                new_session_id,
                parent_session_id,
                reset,
                rewound,
            )
        except Exception as e:
            logger.error(f"on_session_switch failed: {e}")

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
                logger.debug(
                    "on_pre_compress: %d messages preserved", min(20, len(messages))
                )
            else:
                logger.warning("on_pre_compress: store failed")
        except Exception as e:
            logger.error(f"on_pre_compress error: {e}")
        return ""

    def on_delegation(
        self, task: str, result: str, child_session_id: str = "", **kwargs
    ):
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
                    {
                        "role": "assistant",
                        "content": f"[Delegation Result]\n{result[:2000]}",
                    },
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
        """If store count reached threshold, trigger auto-reflection."""
        if not self._agent:
            return
        pending = getattr(self._agent, "_pending_reflection", False)
        if not pending:
            return
        self._agent.clear_pending_reflection()
        # C-M1/P14: keep the reflection scoped to this session's profile and
        # attributed to the actual platform rather than the hardcoded "http".
        self._agent._trigger_auto_reflection(
            self._user_id, profile=self._profile, platform=PLATFORM)

    def on_memory_write(
        self, action: str, target: str, content: str, metadata: Optional[Dict] = None
    ):
        """Mirror Hermes built-in memory write operations.

        Also parses natural language content to extract preferences and habits.
        """
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
            # Parse memory content for preferences and habits
            self._parse_memory_write(content, target)
            logger.info(
                "EchoMind: mirrored memory %s target=%s content_len=%d (ok=%s)",
                action,
                target,
                len(content),
                ok,
            )
        except Exception as e:
            logger.error(
                "EchoMind: on_memory_write failed action=%s target=%s: %s",
                action,
                target,
                e,
            )

    def _parse_memory_write(self, content: str, target: str):
        """Parse natural language memory content for preferences and habits."""
        if not self._agent or not content:
            return
        # 'key=value' syntax: "language=python" → preference
        if "=" in content:
            parts = content.split("=", 1)
            key = parts[0].strip().lower()
            val = parts[1].strip()
            self._agent.user_agent.update(
                self._user_id, "preferences",
                {key: val}, source="memory_tool", profile=self._profile,
            )
            logger.debug("Parsed preference from memory write: %s=%s", key, val)
        # Natural language patterns
        lower = content.lower()
        patterns = [
            (["like ", "prefer ", "喜欢", "偏好"], "preference"),
            (["always ", "usually ", "总是", "通常"], "habit"),
        ]
        for triggers, field in patterns:
            if any(t in lower for t in triggers):
                self._agent.user_agent.update(
                    self._user_id, field,
                    {"note": content[:200]}, source="memory_tool", profile=self._profile,
                )
                break

    # ═══════════════════════════════════════════════════
    # Hermes v0.17.0: Config schema, backup, and save
    # ═══════════════════════════════════════════════════

    def get_config_schema(self) -> List[Dict[str, Any]]:
        """Return config fields for 'hermes memory setup' wizard."""
        return [
            {
                "key": "db_path",
                "description": "SQLite database path for EchoMind memory storage",
                "default": "~/.echomind/memory.db",
                "required": False,
                "secret": False,
            },
            {
                "key": "api_key",
                "description": "API key for EchoMind HTTP API authentication",
                "required": False,
                "secret": True,
                "env_var": "ECHOMIND_API_KEY",
            },
        ]

    def save_config(self, values: Dict[str, Any], hermes_home: str) -> None:
        """Write config to the file EchoMind's server ACTUALLY loads.

        C-M2/P15: previously this wrote flat keys (`api_key`, `db_path`) to
        {hermes_home}/echomind/echomind_config.yaml, but ConfigManager only
        searches ./echomind_config.yaml, ~/.echomind/echomind_config.yaml and
        $ECHOMIND_CONFIG — so the wizard's saved API key was dead config and
        HTTP auth never got enabled. Now we write server.api_key into the real
        search path (same resolution as config_manager._resolve_config_path),
        merging into the existing file instead of clobbering it.
        """
        import os
        # Mirror config_manager._resolve_config_path() so we hit the same file
        # the server actually reads.
        cfg_path = os.environ.get("ECHOMIND_CONFIG")
        if cfg_path:
            config_file = Path(os.path.expanduser(cfg_path))
        else:
            config_file = Path(os.path.expanduser("~/.echomind/echomind_config.yaml"))
        try:
            import yaml
            existing = {}
            if config_file.exists():
                with open(config_file, encoding="utf-8") as f:
                    existing = yaml.safe_load(f) or {}
            server = dict(existing.get("server") or {})
            if not isinstance(server, dict):
                server = {}
            # Wizard returns flat keys: map api_key -> server.api_key
            if "api_key" in values:
                server["api_key"] = values["api_key"]
            existing["server"] = server
            # db_path lives under the storage/db section, not flat
            if values.get("db_path"):
                existing.setdefault("storage", {})["db_path"] = values["db_path"]
            with open(config_file, "w", encoding="utf-8") as f:
                yaml.dump(existing, f, default_flow_style=False)
            logger.info("EchoMind config saved to %s", config_file)
        except ImportError:
            logger.warning("PyYAML not available, cannot save config")
        except Exception as e:
            logger.error("Failed to save EchoMind config: %s", e)

    def backup_paths(self) -> List[str]:
        """Return paths for 'hermes backup' to include EchoMind data."""
        import os
        return [
            os.path.expanduser("~/.echomind/memory.db"),
        ]

    # ═══════════════════════════════════════════════════
    # Internal method
    # ═══════════════════════════════════════════════════

    def _search(self, query: str) -> str:
        """Execute memory search"""
        if not query:
            return "Please provide search keywords"
        # M-5 fix: propagate project/session/profile scope like prefetch does,
        # otherwise search hits the default scope and returns memories from the
        # wrong project/profile, inconsistent with prefetch.
        result = self._agent.retrieve_for_task(
            task_context=query,
            user_id=self._user_id,
            task_id=self._session_id or None,
            platform=PLATFORM,
            project=self._project_id,
            session_id=self._session_id,
            profile=self._profile,
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
            return (
                "User preferences:\n" + "\n".join(lines)
                if lines
                else "No user preference records yet"
            )
        else:
            return json.dumps(user_data, indent=2, ensure_ascii=False, default=str)

    def _format_prefetch_context(self, result: Dict) -> str:
        """Format retrieval results as compact markdown context injection.

        Token-efficient: max 5 memories, one-liner profile, <memory-context> wrapper.
        Compatible with Hermes v0.20+ build_memory_context_block.
        """
        memories = result.get("retrieved_memories", [])
        if not memories:
            return ""

        lines = ["<memory-context>"]

        # One-liner user profile
        user_data = result.get("user", {})
        prefs = user_data.get("preferences", {}) if isinstance(user_data, dict) else {}
        pref_tags = []
        for k in ("response_style", "code_style", "language"):
            v = prefs.get(k)
            if v:
                pref_tags.append(v)
        if pref_tags:
            lines.append(f"**User** ({self._user_id}): {', '.join(pref_tags[:3])}")

        # Memory table — compact, 5 items max
        if memories:
            lines.append("")
            for mem in memories[:5]:
                source = mem.source.replace("_", " ").title()
                content = mem.content[:120].replace("\n", " ").replace("|", "\\|")
                trust = getattr(mem, 'trust_score', None) or 0.5
                lines.append(f"- [{source}][trust={trust:.2f}] {content}")

        lines.append("</memory-context>")
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

    Always returns a string (never None).  Defensive guard: some LLMs
    (e.g. Ollama, DeepSeek) return finish_reason=stop with content=null,
    which would become Python None here.  None would be passed as
    raw_response to _reflect_records, then propagated as the LLM result
    back to the caller, where the caller's OpenAI SDK raises
    EmptyModelOutputError("has no usable output").
    """
    client = _get_llm_client()
    if client is None:
        return ""
    try:
        result = client.chat(prompt)
    except Exception as e:
        logger.warning("Reflection LLM call failed: %s", e)
        return ""
    if result is None or not result.strip():
        return ""
    return result
