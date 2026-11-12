"""Client-side memory hooks (Claude Code, OpenCode) — server-side handlers.

Both clients run thin adapters that POST hook events here; this module owns the
actual work so the logic (identity mapping, recall formatting, idempotent
storage, caps, fail-open) lives in ONE place and is unit-testable without the
clients installed.

Design rules:
  * **Fail-open** — a memory hook must never block the user's turn. The HTTP
    routes catch every exception and return ``{}``.
  * **Idempotent** — Stop, SessionEnd and compaction may all report the same
    completed turn; a deterministic per-turn key plus ``context_exists()``
    prevents duplicate rows without a schema change.
  * **Bounded** — injected context is capped (Claude Code's hard cap is 10k).
  * **Factual** — the block is written as stored facts, never as commands, to
    avoid tripping the client's prompt-injection defenses.
"""

import hashlib
import json
import logging
import os
import threading
from collections import OrderedDict
from typing import Any, Dict, List, Optional

from core.config_manager import get_config_manager
from core.context_block import format_memory_block, records_to_items
from core.storage.sqlite_store import stable_memory_key

logger = logging.getLogger("EchoMind.Hooks")

MAX_CONTEXT_CHARS = 8000
MAX_TRANSCRIPT_MESSAGES = 30
MAX_MESSAGE_CHARS = 4000
TRANSCRIPT_TAIL_BYTES = 512 * 1024

_SEEN_MAX = 4096
_seen: "OrderedDict[str, bool]" = OrderedDict()
_seen_lock = threading.Lock()


# ── identity / config mapping ──────────────────────────────────────────────

def _default_user() -> str:
    try:
        return str(get_config_manager().get_top_level("default_user", "default")
                   or "default")
    except Exception:
        return "default"


def _default_project() -> str:
    try:
        return str(get_config_manager().get_top_level("default_project", "default")
                   or "default")
    except Exception:
        return "default"


def _hook_cfg(key: str, default: Any) -> Any:
    try:
        value = get_config_manager().get("hooks", key, default=default)
        return default if value is None else value
    except Exception:
        return default


def _max_context_chars() -> int:
    try:
        return max(256, min(10000, int(_hook_cfg("max_context_chars", MAX_CONTEXT_CHARS))))
    except (TypeError, ValueError):
        return MAX_CONTEXT_CHARS


def _resolve_user(payload: Dict[str, Any]) -> str:
    explicit = str(payload.get("user_id") or "").strip()
    return (explicit or os.environ.get("ECHOMIND_HOOK_USER", "").strip()
            or _default_user())[:128]


def _resolve_profile(payload: Dict[str, Any]) -> str:
    return str(payload.get("profile")
               or os.environ.get("ECHOMIND_HOOK_PROFILE", "")
               or "default")[:64]


def _resolve_project(payload: Dict[str, Any]) -> str:
    explicit = str(payload.get("project") or "").strip()
    if explicit:
        return explicit[:64]
    configured = str(_hook_cfg("project", "") or "").strip()
    if configured:
        return configured[:64]
    env_project = os.environ.get("ECHOMIND_HOOK_PROJECT", "").strip()
    if env_project:
        return env_project[:64]
    cwd = str(payload.get("cwd") or payload.get("directory") or "").strip()
    if cwd:
        base = os.path.basename(cwd.rstrip("/\\"))
        if base:
            return base[:64]
    return _default_project()[:64]


def _session_id(payload: Dict[str, Any], fallback: str) -> str:
    return str(payload.get("session_id") or "").strip()[:160] or fallback


# ── idempotency ────────────────────────────────────────────────────────────

def _seen_new(key: str) -> bool:
    """True the first time *key* is seen (bounded in-process LRU)."""
    with _seen_lock:
        if key in _seen:
            return False
        _seen[key] = True
        while len(_seen) > _SEEN_MAX:
            _seen.popitem(last=False)
        return True


def _fingerprint(messages: List[Dict[str, str]]) -> str:
    """Stable fingerprint of the completed turn (last assistant reply)."""
    for msg in reversed(messages):
        if msg.get("role") == "assistant" and msg.get("content"):
            return hashlib.sha256(
                msg["content"].encode("utf-8", "replace")).hexdigest()[:16]
    if messages:
        return hashlib.sha256(
            messages[-1]["content"].encode("utf-8", "replace")).hexdigest()[:16]
    return ""


# ── transcript / message normalization ─────────────────────────────────────

def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks = []
        for block in content:
            if isinstance(block, dict) and block.get("type") in ("text", "input_text"):
                text = block.get("text")
                if isinstance(text, str) and text.strip():
                    chunks.append(text)
        return "\n".join(chunks)
    return ""


def read_claude_transcript(path: Optional[str],
                           limit: int = MAX_TRANSCRIPT_MESSAGES) -> List[Dict[str, str]]:
    """Read the tail of a Claude Code JSONL transcript and keep user/assistant text.

    Tool results, system rows and tool-use blocks are dropped: they are large,
    frequently secret-bearing, and not durable user/assistant knowledge.
    """
    if not path or not os.path.isfile(path):
        return []
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            start = max(0, size - TRANSCRIPT_TAIL_BYTES)
            fh.seek(start)
            raw = fh.read().decode("utf-8", "replace")
        lines = raw.splitlines()
        if start > 0 and lines:
            lines = lines[1:]  # first line may be partial
        messages: List[Dict[str, str]] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(obj, dict):
                continue
            msg = obj.get("message") if isinstance(obj.get("message"), dict) else {}
            role = (msg.get("role") or obj.get("role")
                    or (obj.get("type") if obj.get("type") in ("user", "assistant") else ""))
            if role not in ("user", "assistant"):
                continue
            text = _content_to_text(msg.get("content") if msg else obj.get("content"))
            text = text.strip()
            if not text:
                continue
            messages.append({"role": role, "content": text[:MAX_MESSAGE_CHARS]})
        return messages[-limit:]
    except Exception as exc:  # pragma: no cover - filesystem edge cases
        logger.debug("read_claude_transcript failed: %s", exc)
        return []


def normalize_messages(raw: Any) -> List[Dict[str, str]]:
    """Normalize OpenCode/Claude message payloads to ``{role, content}`` dicts."""
    messages: List[Dict[str, str]] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        info = item.get("info") if isinstance(item.get("info"), dict) else {}
        role = item.get("role") or info.get("role")
        content = item.get("content")
        if content is None:
            parts = item.get("parts")
            if isinstance(parts, list):
                content = "\n".join(
                    p.get("text", "") for p in parts
                    if isinstance(p, dict) and p.get("type") == "text")
        if role not in ("user", "assistant"):
            continue
        if not isinstance(content, str) or not content.strip():
            continue
        messages.append({"role": role, "content": content.strip()[:MAX_MESSAGE_CHARS]})
    return messages[-MAX_TRANSCRIPT_MESSAGES:]


# ── recall / briefing ──────────────────────────────────────────────────────

def _recall_block(agent, query: str, user_id: str, profile: str,
                  project: str, session_id: str, client: str) -> (str, int):
    # No query → no recall. Session start uses the dedicated briefing action;
    # an empty query would otherwise return a noisy "preferences: {}" record.
    if not str(query or "").strip():
        return "", 0
    try:
        result = agent.retrieve_for_task(
            task_context=query or "",
            user_id=user_id,
            platform=client,
            project=project,
            session_id=session_id,
            profile=profile,
            max_results=6,
        )
        items = records_to_items(result.get("retrieved_memories", []))
        return format_memory_block(items, max_chars=_max_context_chars()), len(items)
    except Exception as exc:
        logger.warning("hook recall failed (%s): %s", client, exc)
        return "", 0


def _briefing_block(agent, user_id: str, profile: str, project: str) -> (str, int):
    try:
        items = agent.memory_briefing(user_id, profile=profile, project=project)
        return format_memory_block(items, max_chars=_max_context_chars()), len(items)
    except Exception as exc:
        logger.warning("hook briefing failed: %s", exc)
        return "", 0


# ── storage ────────────────────────────────────────────────────────────────

def _store_messages(agent, *, client: str, user_id: str, profile: str,
                    project: str, session_id: str,
                    messages: List[Dict[str, str]],
                    turn_key: Optional[str] = None,
                    extract_knowledge: bool = False) -> Dict[str, Any]:
    messages = normalize_messages(messages)
    if not messages:
        return {"status": "empty"}

    fingerprint = _fingerprint(messages)
    if not fingerprint:
        return {"status": "empty"}
    task_id = turn_key or f"{client}:{session_id}:{fingerprint}"
    ctx_key = stable_memory_key(user_id, task_id)

    # Persistent dedup (survives a process restart): the per-turn context row
    # is written by store() under this stable key.
    try:
        if agent.db.context_exists(ctx_key):
            return {"status": "duplicate"}
    except Exception:
        logger.debug("context_exists check failed", exc_info=True)

    if not _seen_new(f"{client}:{user_id}:{ctx_key}"):
        return {"status": "duplicate"}

    try:
        ok = agent.store(
            user_id=user_id,
            task_id=task_id,
            context=messages,
            task_status="completed",
            success=True,
            platform=client,
            origin_client=client,
            project=project,
            session_id=session_id,
            profile=profile,
            extract_knowledge=extract_knowledge,
        )
        return {"status": "stored" if ok else "error"}
    except Exception as exc:
        logger.warning("hook store failed (%s): %s", client, exc)
        return {"status": "error"}


# ── Claude Code ────────────────────────────────────────────────────────────

def _claude_context(event: str, text: str) -> Dict[str, Any]:
    if not text:
        return {}
    return {"hookSpecificOutput": {
        "hookEventName": event,
        "additionalContext": text,
    }}


def handle_claude_hook(agent, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Handle one Claude Code hook event; always returns hook-shaped JSON."""
    if not isinstance(payload, dict):
        return {}
    event = str(payload.get("hook_event_name") or "").strip()
    user_id = _resolve_user(payload)
    profile = _resolve_profile(payload)
    project = _resolve_project(payload)
    session_id = _session_id(payload, "claude-session")

    if event == "SessionStart":
        text, _n = _briefing_block(agent, user_id, profile, project)
        return _claude_context(event, text)

    if event == "UserPromptSubmit":
        text, _n = _recall_block(
            agent, str(payload.get("prompt") or ""), user_id, profile,
            project, session_id, "claude-code")
        return _claude_context(event, text)

    if event in ("Stop", "SessionEnd", "PreCompact", "SubagentStop"):
        messages = read_claude_transcript(payload.get("transcript_path"))
        _store_messages(
            agent, client="claude-code", user_id=user_id, profile=profile,
            project=project, session_id=session_id, messages=messages,
            extract_knowledge=False)
        return {}

    return {}


# ── OpenCode ───────────────────────────────────────────────────────────────

def handle_opencode_hook(agent, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Handle one OpenCode plugin action (recall / briefing / store)."""
    if not isinstance(payload, dict):
        return {"context": "", "count": 0}
    action = str(payload.get("action") or "recall").strip().lower()
    user_id = _resolve_user(payload)
    profile = _resolve_profile(payload)
    project = _resolve_project(payload)
    session_id = _session_id(payload, "opencode-session")

    if action == "briefing":
        text, count = _briefing_block(agent, user_id, profile, project)
        return {"context": text, "count": count}

    if action == "recall":
        text, count = _recall_block(
            agent, str(payload.get("query") or ""), user_id, profile,
            project, session_id, "opencode")
        return {"context": text, "count": count}

    if action == "store":
        turn = str(payload.get("turn") or "").strip()[:128]
        turn_key = f"opencode:{session_id}:{turn}" if turn else None
        return _store_messages(
            agent, client="opencode", user_id=user_id, profile=profile,
            project=project, session_id=session_id,
            messages=payload.get("messages") or [],
            turn_key=turn_key,
            extract_knowledge=bool(payload.get("extract_knowledge", False)))

    return {"error": f"unknown action: {action}"}
