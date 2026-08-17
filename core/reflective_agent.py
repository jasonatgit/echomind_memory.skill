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
        self._last_reflection: Optional[datetime] = None
        # P5-B: daily reflection quota is tracked per (user_id, UTC date) and
        # persisted to SQLite so it survives restarts and is isolated per user.
        # `_daily_count_map` is a per-process cache of the store's rows; the
        # fallback in-memory path keeps the limit enforced even when a store is
        # not connected (favored over a global scalar shared across all users).
        self._daily_count_map: Dict[Tuple[str, str], int] = {}
        # B10 fix: resolve the daily limit deterministically (midpoint) instead
        # of per-instance random. The old random.uniform gave HTTP vs Hermes
        # processes different limits for the same config, so a user could hit
        # different effective quotas depending on which entrypoint triggered
        # reflection. A deterministic midpoint keeps the [lo, hi] tuning knob
        # while making the limit identical across all instances.
        max_daily = self.config.get("max_daily", [5, 20])
        if isinstance(max_daily, (list, tuple)) and len(max_daily) == 2:
            self._daily_limit = int((max_daily[0] + max_daily[1]) // 2)
        else:
            self._daily_limit = int(max_daily)

    def _today(self) -> str:
        """Current UTC calendar day as ISO yyyy-mm-dd (the daily-limit unit)."""
        return datetime.now(timezone.utc).date().isoformat()

    def _get_daily_count(self, user_id: str) -> int:
        """Authoritative per-(user, today) reflection count.

        When a store is connected the count is ALWAYS re-read from it (audit
        MED-2). The previous version cached per (user, day) once and never
        re-synced, so a `ReflectiveAgent` instance was blind to increments made
        by other instances/processes sharing the DB (HTTP + Hermes running
        together) — each instance independently ran its counter up to the limit,
        overshooting the quota by a multiple. The in-memory `_daily_count_map`
        is now only the no-store (or read-failure) fallback path.
        """
        today = self._today()
        if self.store is not None:
            try:
                count = self.store.get_daily_reflection_count(user_id, today)
                self._daily_count_map[(user_id, today)] = count
                return count
            except Exception:
                pass  # fall back to the in-process cache below
        # No store connected, or the authoritative read failed: use the cache.
        return self._daily_count_map.get((user_id, today), 0)

    def _increment_daily_count(self, user_id: str) -> int:
        """Consume one unit of this user's daily quota and persist it."""
        today = self._today()
        count = self._get_daily_count(user_id) + 1
        # Audit (#7): prune stale (past-day) cache keys so the map stays bounded
        # to at most today's entries in a long-running process. Increments are
        # rare (one per reflection), so the sweep is negligible.
        for k in [k for k in self._daily_count_map if k[1] != today]:
            del self._daily_count_map[k]
        self._daily_count_map[(user_id, today)] = count
        if self.store is not None:
            try:
                # Return the store's authoritative value (reconciles any
                # concurrent increments; audit MED-2). The cache is keyed solely
                # for the no-store fallback.
                return self.store.increment_daily_reflection_count(user_id, today)
            except Exception:
                pass
        return count

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

    def _check_daily_limit(self, user_id: str) -> bool:
        """Return True if this user's daily reflection limit is reached."""
        return self._get_daily_count(user_id) >= self._daily_limit

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
        if self._check_daily_limit(user_id):
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
            self._increment_daily_count(user_id)
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
        if self._check_daily_limit(user_id):
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
            self._increment_daily_count(user_id)
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
