# echomind_memory.skill/core/reflective_agent.py
#
# Self-Reflective Agent


import logging
import threading
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
        # P1-4: serialize quota reservation/refund within this instance (the
        # cross-process guarantee lives in the store's conditional upsert).
        self._quota_lock = threading.Lock()
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

    def refresh_daily_limit(self):
        """Recompute the daily limit from the current config (P2.6).

        The limit was frozen at __init__, so a reflection.max_daily hot-update
        never took effect. Same derivation as __init__: a two-element list is
        the [lo, hi] tuning knob and its midpoint is used.
        """
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

    def _reserve_daily(self, user_id: str) -> bool:
        """Atomically reserve one reflection slot (audit P1-4, reflection side).

        Reserve-before-process: the limit check and the consume are a single
        store-level conditional upsert, so two processes sharing the DB can no
        longer both pass a separate check and both increment past the limit
        (the old check-then-increment TOCTOU). The caller returns the slot via
        ``_refund_daily`` when the reflection fails to produce a consumable
        result, so failed attempts never consume quota.
        """
        today = self._today()
        with self._quota_lock:
            # Prune stale (past-day) cache keys (same as _increment_daily_count).
            for k in [k for k in self._daily_count_map if k[1] != today]:
                del self._daily_count_map[k]
        if self.store is not None:
            try:
                count, allowed = self.store.increment_daily_reflection_count(
                    user_id, today, limit=self._daily_limit)
                with self._quota_lock:
                    self._daily_count_map[(user_id, today)] = count
                return allowed
            except Exception:
                pass  # fall back to the in-process path below
        # No store connected, or the authoritative op failed: in-process check-
        # then-increment under the quota lock (best effort, single instance).
        with self._quota_lock:
            count = self._daily_count_map.get((user_id, today), 0)
            if count >= self._daily_limit:
                return False
            self._daily_count_map[(user_id, today)] = count + 1
            return True

    def _refund_daily(self, user_id: str) -> None:
        """Return one reserved slot (floor 0) after a failed reflection."""
        today = self._today()
        with self._quota_lock:
            count = self._daily_count_map.get((user_id, today), 0)
            self._daily_count_map[(user_id, today)] = max(0, count - 1)
        if self.store is not None:
            try:
                self.store.decrement_daily_reflection_count(user_id, today)
            except Exception:
                pass

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
        if not self._reserve_daily(user_id):
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
        output = None
        if result is not None and not isinstance(result, tuple):
            self._last_reflection = datetime.now(timezone.utc)
            if isinstance(result, dict):
                from .models.reflection import ReflectionOutput
                try:
                    output = ReflectionOutput(**result)
                except Exception:
                    logger.warning("reflect_with_llm: failed to coerce dict to ReflectionOutput")
                    output = None
            elif isinstance(result, str):
                # Raw string from fallback — not a valid reflection output
                output = None
            else:
                output = result
        if output is None:
            # P1-4: the reserved slot is refunded so failed reflections
            # (parse failure / low confidence / coercion failure) never
            # consume quota.
            self._refund_daily(user_id)
        return output

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
        if not self._reserve_daily(user_id):
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
        output = None
        if result is not None:
            self._last_reflection = datetime.now(timezone.utc)
            if isinstance(result, dict):
                from .models.reflection import ReflectionOutput
                try:
                    output = ReflectionOutput(**result)
                except Exception:
                    logger.warning("process_result: failed to coerce dict to ReflectionOutput")
                    output = None
            elif isinstance(result, str):
                output = None
            else:
                output = result
        if output is None:
            # P1-4: refund the reserved slot — a parse failure / low-confidence
            # result must not consume quota, and the endpoint's post-hoc
            # _check_daily_limit then correctly reports 400 (not 429).
            self._refund_daily(user_id)
        return output
