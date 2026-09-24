"""Memory lifecycle state machine (v1.2.18 refactor, P2).

Extracted from MainMemoryAgent. Owns the Ebbinghaus-driven Active → Stale →
Archived transitions plus the knowledge cognitive_pos (nok/fok/exo) migration.

MainMemoryAgent holds one instance (`self.lifecycle`) and its
`_update_memory_states` / `_migrate_cognitive_pos` methods delegate here, so
call sites are unchanged.
"""

import logging
from typing import Callable

logger = logging.getLogger("MemoryAgent")


class MemoryLifecycle:
    """Freshness-driven lifecycle transitions for the four scan tables."""

    # Thresholds (mirror MainMemoryAgent class defaults).
    FRESHNESS_STALE_THRESHOLD = 0.3
    FRESHNESS_ARCHIVE_THRESHOLD = 0.1
    COGNITIVE_FOK_THRESHOLD = 0.3
    COGNITIVE_EXO_THRESHOLD = 0.1

    def __init__(self, db, knowledge_agent, cfg, freshness_fn: Callable,
                 persistence_enabled_fn: Callable,
                 *, stale_threshold: float = None, archive_threshold: float = None,
                 cognitive_fok_threshold: float = None,
                 cognitive_exo_threshold: float = None):
        self.db = db
        self.knowledge_agent = knowledge_agent
        self.cfg = cfg
        self._freshness = freshness_fn
        self._persistence_enabled = persistence_enabled_fn
        if stale_threshold is not None:
            self.FRESHNESS_STALE_THRESHOLD = stale_threshold
        if archive_threshold is not None:
            self.FRESHNESS_ARCHIVE_THRESHOLD = archive_threshold
        if cognitive_fok_threshold is not None:
            self.COGNITIVE_FOK_THRESHOLD = cognitive_fok_threshold
        if cognitive_exo_threshold is not None:
            self.COGNITIVE_EXO_THRESHOLD = cognitive_exo_threshold

    def update_memory_states(self, user_id: str = ""):
        """Scan recent memories and update states based on Ebbinghaus freshness.

        Maps freshness scores to states:
          freshness 0.1-0.3 → stale
          freshness < 0.1  → archived
        Transitions: active→stale, active/stale→archived.

        Knowledge entries additionally migrate cognitive_pos (nok/fok/exo) in
        lockstep with the freshness decay, using independent thresholds so the
        cognitive-position axis can be tuned separately from lifecycle state.
        """
        if not self._persistence_enabled() or not self.db._conn:
            return
        try:
            limit = self.cfg.get("retrieval", "state_scan_limit", default=1000)
        except Exception:
            limit = 1000
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 1000
        try:
            for mem_type, table, id_col in [
                ("knowledge", "knowledge_memory", "id"),
                ("experience", "experience_memory", "id"),
                ("task", "task_memory", "id"),
                ("context", "context_memory", "session_id"),
            ]:
                with self.db._lock:
                    # P1-7 (v1.2.16 audit): the scan was NOT user-scoped — a
                    # single retrieve_for_task/store on any account swept EVERY
                    # user's most recent rows and let one user's activity push
                    # another user's idle memories into stale/archived. Every
                    # one of the four tables carries user_id, so the scan is now
                    # bound to the acting user (multi-tenant hygiene).
                    rows = self.db._conn.execute(
                        f"SELECT {id_col} as rid, created_at, last_access_at "
                        f"FROM {table} WHERE user_id = ? "
                        f"ORDER BY created_at DESC LIMIT ?",
                        (user_id, limit),
                    ).fetchall()
                # Batch the lifecycle transitions in one transaction (P1-7):
                # previously each transition committed independently and the
                # whole scan was a cross-user side effect on the hot path.
                # save_memory_state's _maybe_commit no-ops inside a batch, so
                # the COMMITs collapse to a single one on exit.
                with self.db.transaction():
                    for r in rows:
                        current = self.db.get_memory_state(mem_type, r["rid"])
                        if current in ("archived", "superseded"):
                            continue
                        freshness = self._freshness(dict(r))
                        if freshness < self.FRESHNESS_ARCHIVE_THRESHOLD:
                            if current in ("active", "stale"):
                                self.db.save_memory_state(mem_type, r["rid"], "archived",
                                                           "freshness_decay", source="system")
                        elif freshness < self.FRESHNESS_STALE_THRESHOLD and current == "active":
                            self.db.save_memory_state(mem_type, r["rid"], "stale",
                                                      "freshness_decay", source="system")
                # cognitive_pos lifecycle (knowledge only) — truly OUTSIDE the
                # batch (P1-4 v1.2.17 review: the earlier "outside" comment was
                # aspirational; the loop actually sat inside the `with`). It
                # takes db._lock itself and is swallowed-by-design, so running
                # it after the batch keeps the transaction boundary exactly the
                # four-table state transitions and nothing else.
                if mem_type == "knowledge":
                    for r in rows:
                        current = self.db.get_memory_state(mem_type, r["rid"])
                        if current in ("archived", "superseded"):
                            continue
                        self.migrate_cognitive_pos(r["rid"], self._freshness(dict(r)))
        except Exception as e:
            # F2 (v1.2.15 audit): data-loss path (zero lifecycle transitions);
            # it must be observable, not debug-silent.
            logger.warning("Memory state update skipped: %s", e)

    def migrate_cognitive_pos(self, knowledge_id: str, freshness: float):
        """Migrate a knowledge entry's cognitive_pos by freshness.

        nok (current context) → fok (fading) → exo (external deep memory).
        Persists to both the DB metadata JSON and the in-memory agent so the
        markdown archive reflects the migration without a reload.
        """
        if freshness < self.COGNITIVE_EXO_THRESHOLD:
            new_pos = "exo"
        elif freshness < self.COGNITIVE_FOK_THRESHOLD:
            new_pos = "fok"
        else:
            new_pos = "nok"
        try:
            with self.db._lock:
                self.db._conn.execute(
                    "UPDATE knowledge_memory SET metadata = json_set("
                    "CASE WHEN json_type(metadata) IS NULL THEN '{}' ELSE metadata END, "
                    "'$.cognitive_pos', ?) WHERE id = ?",
                    (new_pos, knowledge_id),
                )
            self.db._maybe_commit()
        except Exception as e:
            logger.debug("cognitive_pos DB migration failed: %s", e)
        entry = self.knowledge_agent.store.get(knowledge_id)
        if entry is not None:
            entry.metadata["cognitive_pos"] = new_pos
