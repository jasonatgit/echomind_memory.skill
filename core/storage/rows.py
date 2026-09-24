"""Row normalization + safe JSON helpers for the SQLite layer (v1.2.18, P3).

Extracted from core/storage/sqlite_store.py. Re-exported there so existing
references keep working.
"""

import json
from typing import Dict

# Text columns that should never be None when loaded from DB
# (ALTER TABLE ADD COLUMN leaves NULL in existing rows even with DEFAULT)
_NULLABLE_TEXT_COLS = {
    "session_id", "session_title", "project", "profile", "platform",
    "language", "compressed_summary",
    # JSON columns: ALTER TABLE ADD COLUMN leaves NULL
    "preferences", "habits", "history",
    "steps", "metadata", "tags",
    "steps_sequence",
    "messages",
    "prerequisites", "output_template",
    "authors", "keywords", "key_points",
    "linked_papers",
    "key_decisions",
}

# Default values for JSON columns when NULL is encountered
_JSON_DEFAULTS = {
    "preferences": "{}", "habits": "{}", "history": "[]",
    "steps": "[]", "metadata": "{}", "tags": "[]",
    "steps_sequence": "[]",
    "messages": "[]",
    "prerequisites": "[]", "output_template": "",
    "authors": "[]", "keywords": "[]", "key_points": "[]",
    "linked_papers": "[]",
    "key_decisions": "[]",
}


def _normalize_row(row) -> Dict:
    """Normalize None values in text columns to empty string/json default.
    Returns a mutable dict (converts sqlite3.Row if needed)."""
    if not isinstance(row, dict):
        row = dict(row)
    for k in list(row.keys()):
        if k in _NULLABLE_TEXT_COLS and row[k] is None:
            row[k] = _JSON_DEFAULTS.get(k, "")
    return row


def _safe_json_loads(value, default):
    """Parse a JSON column safely; return default on malformed input."""
    if value is None:
        return default
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default
