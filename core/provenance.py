# EchoMind — Provenance helpers (v1.2.14)
#
# Shared, dependency-free helpers for memory provenance and tag handling:
#
#   * normalize_tags / tags_match      — tag storage + case-insensitive matching
#   * normalize_origin_client          — "who produced this memory" normalization
#   * ORIGIN_PLATFORMS / KNOWN_CLIENTS — canonical vocabularies
#   * build_envelope                   — the provenance envelope written next to
#                                        every stored record (metadata.envelope)
#
# Design notes (v1.2.14 plan, section 3):
#   * Tags keep their ORIGINAL case in storage; matching is case-insensitive
#     (casefold) so "Python" and "python" do not split into two tags.
#   * origin_client is a free-form string with a known-value normalization:
#     known clients are lower-cased to their canonical form, unknown values are
#     preserved verbatim (after stripping) so bespoke clients stay identifiable.

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

# ── Vocabularies ─────────────────────────────────────────

# Transport that delivered the write.
ORIGIN_PLATFORMS = ("mcp", "http", "hermes", "cli")

# Known source clients → canonical (lower-case) spelling. Lookup is done on the
# casefolded, separator-normalized value so "Claude Code", "claude_code" and
# "Claude-Code" all land on "claude-code".
KNOWN_CLIENTS = {
    "claude-code": "claude-code",
    "claudecode": "claude-code",
    "claude": "claude-code",
    "opencode": "opencode",
    "open-code": "opencode",
    "hermes": "hermes",
    "openclaw": "openclaw",
    "open-claw": "openclaw",
    "dsh": "dsh",
    "unknown": "unknown",
}

# ── Limits (v1.2.14 plan, confirmed) ─────────────────────

MAX_TAGS = 12
MAX_TAG_LEN = 32


def _norm_token(value: str) -> str:
    """Casefold + normalize separators/spaces for vocabulary lookups.

    "Claude Code", "claude_code" and "Claude-Code" all land on "claude-code".
    """
    return " ".join(value.split()).casefold().replace(" ", "-").replace("_", "-")


def normalize_tags(raw: Optional[Iterable[Any]],
                   max_tags: int = MAX_TAGS,
                   max_tag_len: int = MAX_TAG_LEN) -> List[str]:
    """Normalize a raw tag payload for storage.

    - strips surrounding whitespace, drops empties
    - de-duplicates case-insensitively (``casefold``) while keeping the FIRST
      spelling seen, so the original case is preserved on the stored tag
    - truncates each tag to ``max_tag_len`` characters
    - caps the list at ``max_tags`` entries

    Never raises: non-iterable input returns an empty list; a bare string is
    treated as a single tag (not iterated per character).
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple, set, frozenset)):
        return []

    out: List[str] = []
    seen: set = set()
    for item in raw:
        if item is None:
            continue
        tag = str(item).strip()
        if not tag:
            continue
        if len(tag) > max_tag_len:
            tag = tag[:max_tag_len].strip()
            if not tag:
                continue
        key = tag.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(tag)
        if len(out) >= max_tags:
            break
    return out


def merge_tags(user_tags: Optional[Iterable[Any]],
               auto_tags: Optional[Iterable[Any]]) -> List[str]:
    """Merge caller-supplied tags (priority, order-preserving) with auto tags.

    v1.2.14 requirement: "caller-supplied first, auto-extracted as fallback".
    The union keeps the caller's tags first and lets the automatic ones fill
    the remainder (case-insensitive dedup across both).
    """
    merged = normalize_tags(user_tags) + normalize_tags(auto_tags)
    return normalize_tags(merged)


def tags_match(entry_tags: Optional[Iterable[Any]],
               query_tags: Optional[Iterable[Any]],
               match_all: bool = False) -> bool:
    """Case-insensitive tag match.

    - ``query_tags`` empty/None → True (no filtering)
    - ``match_all=False`` (default) → OR semantics: any query tag present
    - ``match_all=True`` → AND semantics: every query tag present

    Entries with no tags match only when no query tags are given.
    """
    query = normalize_tags(query_tags)
    if not query:
        return True
    entry = {str(t).strip().casefold() for t in (entry_tags or []) if str(t).strip()}
    if not entry:
        return False
    wanted = {t.casefold() for t in query}
    if match_all:
        return wanted.issubset(entry)
    return bool(wanted & entry)


def normalize_origin_client(raw: Optional[str], default: str = "unknown") -> str:
    """Normalize a source-client value.

    Known clients (claude-code / opencode / hermes / openclaw / dsh / unknown)
    are canonicalized; unknown values are preserved verbatim (stripped) so
    bespoke clients remain identifiable. Empty/None → ``default``.
    """
    if raw is None:
        return default
    value = str(raw).strip()
    if not value:
        return default
    return KNOWN_CLIENTS.get(_norm_token(value), value)


def normalize_origin_platform(raw: Optional[str], default: str = "") -> str:
    """Normalize the transport value; unknown transports are lower-cased."""
    if raw is None:
        return default
    value = str(raw).strip()
    if not value:
        return default
    return value.casefold()


def build_envelope(origin_platform: Optional[str] = None,
                   origin_client: Optional[str] = None,
                   project: Optional[str] = None,
                   tags: Optional[Iterable[Any]] = None,
                   session_id: Optional[str] = None,
                   task_id: Optional[str] = None,
                   captured_at: Optional[str] = None) -> Dict[str, Any]:
    """Build the provenance envelope stored with a memory record.

    ``schema`` lets a future reader interpret the envelope without guessing.
    ``captured_at`` defaults to the current UTC time in ISO-8601.
    """
    return {
        "schema": "envelope-v1",
        "origin_platform": normalize_origin_platform(origin_platform),
        "origin_client": normalize_origin_client(origin_client),
        "project": project or "default",
        "tags": normalize_tags(tags),
        "session_id": session_id or "",
        "task_id": task_id or "",
        "captured_at": captured_at or datetime.now(timezone.utc).isoformat(),
    }


def envelope_from_record(meta: Any) -> Optional[Dict[str, Any]]:
    """Extract the provenance envelope from a record's metadata.

    Handles the three nestings that occur in practice:
    - direct: ``meta["envelope"]`` (knowledge kb_metadata, in-memory rows)
    - nested: ``meta["metadata"]["envelope"]`` (knowledge/experience search
      results embed the entry's own metadata dict one level down)
    - fallback: rebuild a minimal envelope from origin_platform/origin_client
      fields (rows stored before the envelope existed) so exports and tool
      output still show a source line instead of nothing.

    Returns the envelope dict or None when nothing origin-related is present.
    """
    if not isinstance(meta, dict):
        return None
    env = meta.get("envelope")
    if isinstance(env, dict):
        return env
    inner = meta.get("metadata")
    if isinstance(inner, dict):
        env = inner.get("envelope")
        if isinstance(env, dict):
            return env
        # Fallback: flat origin fields on the embedded entry metadata.
        platform = str(inner.get("origin_platform") or "").strip()
        client = str(inner.get("origin_client") or "").strip()
        if platform or client:
            return {"schema": "envelope-v1-fallback",
                    "origin_platform": platform,
                    "origin_client": client,
                    "project": inner.get("project", ""),
                    "tags": inner.get("tags") or []}
    # Fallback: flat origin fields on the record metadata itself (context rows).
    platform = str(meta.get("origin_platform") or "").strip()
    client = str(meta.get("origin_client") or "").strip()
    if platform or client:
        return {"schema": "envelope-v1-fallback",
                "origin_platform": platform,
                "origin_client": client,
                "project": meta.get("project", ""),
                "tags": meta.get("tags") or []}
    return None


def format_origin_line(envelope: Optional[Dict[str, Any]],
                       created_at: Optional[str] = None) -> str:
    """Render a compact provenance prefix.

    e.g. ``[2026-09-13][mcp/claude-code][projectsA][代码习惯]``.

    Used by markdown export and tool output so the source of every memory is
    visible at a glance. Returns ``""`` when there is nothing to show.
    """
    env = envelope if isinstance(envelope, dict) else {}
    platform = str(env.get("origin_platform") or "").strip()
    client = str(env.get("origin_client") or "").strip()
    project = str(env.get("project") or "").strip()
    tags = normalize_tags(env.get("tags"))
    date = str(created_at or env.get("captured_at") or "").strip()[:10]

    parts: List[str] = []
    if date:
        parts.append(date)
    transport = "/".join(p for p in (platform, client) if p)
    if transport:
        parts.append(transport)
    if project and project != "default":
        parts.append(project)
    if tags:
        parts.append(",".join(tags))
    if not parts:
        return ""
    return "[" + "][".join(parts) + "]"
