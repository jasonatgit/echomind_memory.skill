"""Stable composite keys for task-scoped records (v1.2.18 refactor, P3).

Extracted from core/storage/sqlite_store.py. Re-exported there so existing
imports (`from core.storage.sqlite_store import stable_memory_key`) keep working.
"""

import hashlib


def stable_memory_key(user_id: str, task_id: str) -> str:
    """Deterministic, delimiter-safe composite key for task-scoped records.

    B5/B6 fix: task_id itself can contain ':' (e.g. Hermes "{session}:turn{n}"),
    so the old f"{user_id}:{task_id}" made the primary key ambiguous and
    impossible to split reliably — breaking delete/state lookups. This hashes
    the pair with a NUL separator so the key is unambiguous and stable across
    every call site (task_memory.id, context_memory.session_id,
    knowledge_memory.id, memory_states.memory_id).
    """
    digest = hashlib.sha256(f"{user_id}\x00{task_id}".encode("utf-8")).hexdigest()
    return f"t:{digest[:24]}"
