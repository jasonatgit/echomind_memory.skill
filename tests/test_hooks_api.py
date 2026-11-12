"""Regression tests for the client hook adapters (v1.2.21).

Covers Claude Code and OpenCode hook handling: recall/briefing shape, the
context cap, idempotent per-turn storage, project mapping and fail-open
behavior. No client binaries are required.
"""

import json


# ── pure formatting ────────────────────────────────────────────────────────

def test_format_memory_block_is_bounded_and_tagged():
    from core.context_block import format_memory_block
    items = [{"source": "knowledge", "content": "x" * 600} for _ in range(100)]
    block = format_memory_block(items, max_chars=8000)
    assert block.startswith("<echomind-memory>")
    assert block.endswith("</echomind-memory>")
    assert len(block) <= 8000


def test_format_memory_block_empty_when_no_items():
    from core.context_block import format_memory_block
    assert format_memory_block([]) == ""
    assert format_memory_block([{"source": "x", "content": "   "}]) == ""


# ── briefing / project mapping ─────────────────────────────────────────────

def test_memory_briefing_includes_sources(memory_agent):
    a = memory_agent
    a.user_agent.update("briefuser", "preferences", {"response_style": "concise"})
    a.knowledge_agent.add_document(
        "Docker builds should use multi-stage images",
        {"user_id": "briefuser", "domain": "devops", "trust_score": 0.9},
    )
    a.experience_agent.store_experience(
        "briefuser", "t1", "general", True, ["step"], "Fixed the docker build")

    items = a.memory_briefing("briefuser", project=None)
    sources = {i["source"] for i in items}
    assert "user" in sources
    assert "knowledge" in sources
    assert "experience" in sources
    assert any("multi-stage" in i["content"] for i in items)


def test_project_mapping_uses_cwd_basename():
    from adapters.hooks_api import _resolve_project
    assert _resolve_project({"cwd": "/home/jason/projects/myproj"}) == "myproj"
    assert _resolve_project({"project": "explicit"}) == "explicit"


# ── Claude Code hooks ──────────────────────────────────────────────────────

def test_claude_session_start_returns_context(memory_agent):
    from adapters.hooks_api import handle_claude_hook
    memory_agent.knowledge_agent.add_document(
        "The deploy target is production", {"user_id": "cuser", "trust_score": 0.9})

    out = handle_claude_hook(memory_agent, {
        "hook_event_name": "SessionStart",
        "session_id": "s1",
        "cwd": "/tmp/proj",
        "user_id": "cuser",
    })
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "production" in ctx


def test_claude_user_prompt_recall(memory_agent):
    from adapters.hooks_api import handle_claude_hook
    memory_agent.knowledge_agent.add_document(
        "Use ruff for Python linting", {"user_id": "cuser2"})

    out = handle_claude_hook(memory_agent, {
        "hook_event_name": "UserPromptSubmit",
        "session_id": "s2",
        "cwd": "/tmp/proj",
        "user_id": "cuser2",
        "prompt": "how should I lint python?",
    })
    assert "ruff" in out["hookSpecificOutput"]["additionalContext"].lower()


def test_claude_stop_store_idempotent(memory_agent, tmp_path):
    from adapters.hooks_api import handle_claude_hook
    transcript = tmp_path / "t.jsonl"
    transcript.write_text("\n".join([
        json.dumps({"type": "user", "message": {"role": "user", "content": "hello"}}),
        json.dumps({"type": "assistant",
                    "message": {"role": "assistant", "content": "world answer"}}),
    ]), encoding="utf-8")
    payload = {
        "hook_event_name": "Stop",
        "session_id": "stop-session",
        "cwd": "/tmp/stop-proj",
        "user_id": "stopuser",
        "transcript_path": str(transcript),
    }
    handle_claude_hook(memory_agent, payload)
    handle_claude_hook(memory_agent, payload)  # same turn → duplicate, no second row

    rows = memory_agent.db._conn.execute(
        "SELECT COUNT(*) FROM context_memory WHERE user_id=?",
        ("stopuser",)).fetchone()[0]
    assert rows == 1


# ── OpenCode hooks ─────────────────────────────────────────────────────────

def test_opencode_recall_action(memory_agent):
    from adapters.hooks_api import handle_opencode_hook
    memory_agent.knowledge_agent.add_document(
        "OpenCode plugins can inject session context", {"user_id": "ouser"})

    out = handle_opencode_hook(memory_agent, {
        "action": "recall",
        "session_id": "os1",
        "cwd": "/tmp/oproj",
        "user_id": "ouser",
        "query": "opencode plugin context",
    })
    assert out["count"] >= 1
    assert "inject session context" in out["context"]


def test_opencode_store_idempotent(memory_agent):
    from adapters.hooks_api import handle_opencode_hook
    payload = {
        "action": "store",
        "session_id": "os2",
        "cwd": "/tmp/oproj",
        "user_id": "ouser2",
        "turn": "msg-1",
        "messages": [
            {"role": "user", "content": "do it"},
            {"role": "assistant", "content": "done"},
        ],
    }
    first = handle_opencode_hook(memory_agent, payload)
    second = handle_opencode_hook(memory_agent, payload)
    assert first["status"] == "stored"
    assert second["status"] == "duplicate"

    rows = memory_agent.db._conn.execute(
        "SELECT COUNT(*) FROM context_memory WHERE user_id=?",
        ("ouser2",)).fetchone()[0]
    assert rows == 1


def test_hook_handlers_fail_open_on_bad_payload(memory_agent):
    from adapters.hooks_api import handle_claude_hook, handle_opencode_hook
    assert handle_claude_hook(memory_agent, {}) == {}
    out = handle_opencode_hook(memory_agent, {})
    assert isinstance(out, dict)
    assert "context" in out


# ── storage helper ─────────────────────────────────────────────────────────

def test_context_exists(sqlite_store):
    sqlite_store.save_context("sess-x", "u", [{"role": "user", "content": "hi"}])
    assert sqlite_store.context_exists("sess-x") is True
    assert sqlite_store.context_exists("missing") is False
