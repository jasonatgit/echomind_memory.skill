# echomind_memory.skill/core/reflective_agent.py
#
# Self-Reflective Agent


import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional, Callable, Union, Tuple

logger = logging.getLogger("ReflectiveAgent")

_engine = None

try:
    from . import _native_engine as _engine
except ImportError:
    try:
        from . import _reflective_fallback as _engine
    except ImportError:
        _engine = None


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
        self._daily_count_date = datetime.now(timezone.utc).date()
        # Fix daily limit once at init (was previously re-randomized on every call)
        max_daily = self.config.get("max_daily", [5, 20])
        if isinstance(max_daily, (list, tuple)):
            import random as _rng
            self._daily_limit = int(_rng.uniform(max_daily[0], max_daily[1]))
        else:
            self._daily_limit = int(max_daily)

    def _reset_daily_if_new_day(self):
        """Reset the daily reflection counter when the UTC calendar day changes.
        Prevents the 'daily' limit from becoming a process-lifetime cap."""
        today = datetime.now(timezone.utc).date()
        if today != self._daily_count_date:
            self._daily_count = 0
            self._daily_count_date = today

    # ── Engine status detection ──

    @staticmethod
    def is_native_engine_available() -> bool:
        """Return True if the native reflection engine module is available."""
        try:
            from . import _native_engine
            return True
        except ImportError:
            return False

    @staticmethod
    def get_engine_status() -> dict:
        """Return engine capabilities as a dict."""
        if ReflectiveAgent.is_native_engine_available():
            return {"engine": "native", "build_prompt_available": True, "merge_active": True}
        if _engine is not None:
            return {"engine": "keyword", "build_prompt_available": False, "merge_active": False}
        return {"engine": "none", "build_prompt_available": False, "merge_active": False}

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
            return "", [r.get("id", f"rec_{i}") for i, r in enumerate(records)]
        result = _engine._reflect_records(
            records,
            user_id,
            platform,
            None,
            self.config,
            self.store,
            self.memory,
        )
        if isinstance(result, tuple) and len(result) == 2:
            return result
        if isinstance(result, dict) and result.get("source") == "keyword":
            if hasattr(_engine, '_prepare_reflection_context'):
                return _engine._prepare_reflection_context(records), [r.get("id", f"rec_{i}") for i, r in enumerate(records)]
            return "", [r.get("id", f"rec_{i}") for i, r in enumerate(records)]
        return "", [r.get("id", f"rec_{i}") for i, r in enumerate(records)]

    # ── Hermes auto path: engine calls LLM internally ──

    def _check_daily_limit(self) -> bool:
        """Return True if daily reflection limit reached."""
        self._reset_daily_if_new_day()
        return self._daily_count >= self._daily_limit

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
            return None
        if self._check_daily_limit():
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
        # Unify return type to ReflectionOutput (never return raw dict/str)
        if isinstance(result, dict):
            from .models.reflection import ReflectionOutput

            try:
                return ReflectionOutput(**result)
            except Exception:
                logger.warning("reflect_with_llm: failed to coerce dict to ReflectionOutput")
                return None
        if isinstance(result, str):
            # Raw string from fallback — not a valid reflection output
            return None
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
        if self._check_daily_limit():
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
            if isinstance(result, dict):
                from .models.reflection import ReflectionOutput
                try:
                    return ReflectionOutput(**result)
                except Exception:
                    logger.warning("process_result: failed to coerce dict to ReflectionOutput")
                    return None
            if isinstance(result, str):
                return None
        return result
