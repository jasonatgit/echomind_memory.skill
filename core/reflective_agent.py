# echomind_memory.skill/core/reflective_agent.py
#
# Self-Reflective Agent


import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional, Callable, Union, Tuple

logger = logging.getLogger("ReflectiveAgent")

_engine = None

try:
    from . import _reflective_core as _engine
    logger.info("Reflection engine: native compiled extension loaded")
except ImportError:
    try:
        from . import _reflective_fallback as _engine
        logger.info("Reflection engine: Python fallback loaded")
    except ImportError:
        _engine = None
        logger.warning("Reflection engine: NOT available")

# All methods use _engine is None as the single source of truth


class ReflectiveAgent:

    def __init__(self, store, memory_agent, config: dict = None):
        self.store = store
        self.memory = memory_agent
        if config is not None:
            self.config = config
        else:
            from .config_manager import get_config_manager

            cfg = get_config_manager()
            self.config = cfg.get_section("reflection")
        self._daily_count = 0
        self._last_reflection: Optional[datetime] = None

    # ── Two-phase HTTP API: build prompt, caller processes externally ──

    def build_prompt(
        self,
        records: List[Dict],
        user_id: str,
        platform: str,
    ) -> Tuple[str, List[str]]:
        """Build reflection prompt for caller-side LLM processing.

        Returns (prompt: str, record_ids: list).
        Used by HTTP API /api/reflect endpoint (llm_response=None).
        """
        if _engine is None:
            logger.info("Reflection build_prompt: engine unavailable")
            return "", [r.get("id", f"rec_{i}") for i, r in enumerate(records)]
        result = _engine._reflect_records(
            records,
            user_id,
            platform,
            None,  # llm_fn=None → engine returns (prompt, ids) tuple
            self.config,
            self.store,
            self.memory,
        )
        if isinstance(result, tuple) and len(result) == 2:
            return result
        # Unexpected: engine returned non-tuple → treat as no prompt
        return "", [r.get("id", f"rec_{i}") for i, r in enumerate(records)]

    # ── Hermes auto path: engine calls LLM internally ──

    def reflect_with_llm(
        self,
        records: List[Dict],
        user_id: str,
        platform: str,
        llm_fn: Callable[[str], str],
    ):
        """Run full reflection cycle with an internal LLM function.

        Returns ReflectionOutput or None.
        Used by Hermes provider (on_session_end → _hermes_llm_fn).
        """
        if _engine is None:
            logger.info("Reflection skipped: engine unavailable")
            return None
        result = _engine._reflect_records(
            records,
            user_id,
            platform,
            llm_fn,
            self.config,
            self.store,
            self.memory,
        )
        if result is not None and not isinstance(result, tuple):
            self._daily_count += 1
            self._last_reflection = datetime.now(timezone.utc)
        return result

    # ── Two-phase HTTP API (phase 2): process LLM response ──

    def process_result(
        self,
        raw_response: str,
        records: List[Dict],
        user_id: str,
        platform: str,
    ):
        """Parse and merge LLM response back into memory."""
        if _engine is None:
            return None
        result = _engine._process_reflection(
            raw_response,
            records,
            user_id,
            platform,
            self.config,
            self.store,
            self.memory,
        )
        if result is not None:
            self._daily_count += 1
            self._last_reflection = datetime.now(timezone.utc)
        return result
