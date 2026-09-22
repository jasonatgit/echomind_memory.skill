#!/usr/bin/env python3
# EchoMind Memory — Unified entry point
#
# HTTP mode (Default): python3 main.py
#   start FastAPI service for Hermes / OpenClaw / OpenCode / Claude Code passed HTTP calls
#
# Hermes call() mode: from main import call
#   Direct tool function calls for Hermes skill.yaml dispatch
#
# MCP mode: python3 main.py --mcp
#   start MCP stdio service（future implementation）

import sys
import os
import atexit
import logging

logger = logging.getLogger("EchoMind.main")

_pkg_dir = os.path.dirname(os.path.abspath(__file__))
if _pkg_dir not in sys.path:
    sys.path.insert(0, _pkg_dir)

# Module-level agent cache: keyed by resolved config_path
_call_agents: dict = {}
# P2-17 (v1.2.16 audit): each unique config_path builds an agent that holds an
# open SQLite connection; a long-running Hermes REPL that rotates config paths
# would grow this dict without bound. Keep the most recent _CALL_AGENTS_MAX
# agents; on eviction disable persistence (closes the DB connection) so the
# memory no longer leaks file descriptors.
_CALL_AGENTS_MAX = 8


def _evict_call_agent(path: str):
    """Shut down one cached (agent, cfg) pair and drop it from the cache.

    Runs while the pair is still inserted, then removes it. Used when the
    cache exceeds _CALL_AGENTS_MAX and on process exit.
    """
    pair = _call_agents.get(path)
    if pair is None:
        return
    agent, _cfg = pair
    try:
        agent.shutdown()
    except Exception:
        logger.exception("evict call-agent for %s failed", path)
    _call_agents.pop(path, None)


def _default_user_id() -> str:
    """Configured default identity when a tool call omits user_id."""
    try:
        from core.config_manager import get_config_manager
        return get_config_manager().get_top_level("default_user", "cli") or "cli"
    except Exception:
        return "cli"


def call(tool_name: str, config_path: str = None, **kwargs):
    """Hermes skill.yaml Dispatch entry point

    Supported tools: retrieve_memory, store_memory, record_feedback,
    query_memory, sync_code_memory, add_research_paper, add_research_note

    Config path priority:
        call(config_path="./prod.yaml", ...)   ← explicitly passed
        ECHOMIND_CONFIG environment variable               ← environment variable
        ~/.echomind/echomind_config.yaml       ← HOME Default
    """
    from core.config_manager import ConfigManager, get_config_manager
    from core.memory_agent import MainMemoryAgent

    # Resolve config path for cache key
    if config_path:
        resolved = os.path.expanduser(config_path)
    else:
        resolved = os.environ.get("ECHOMIND_CONFIG") or os.path.expanduser("~/.echomind/echomind_config.yaml")

    # Cache hit: reuse agent (avoids re-creating DB connection per call)
    if resolved not in _call_agents:
        cfg = ConfigManager(config_path=resolved) if config_path else get_config_manager()
        agent = MainMemoryAgent(config_manager=cfg)
        agent.enable_persistence()
        cfg.on_reload(agent.refresh_config)
        _call_agents[resolved] = (agent, cfg)
        # P2-17: bound the cache — evict the OLDEST entry (dict preserves
        # insertion order) beyond _CALL_AGENTS_MAX. Only one eviction per new
        # insert keeps the bound tight while never degrading the hot path.
        if len(_call_agents) > _CALL_AGENTS_MAX:
            _evict_call_agent(next(iter(_call_agents)))
    else:
        agent, cfg = _call_agents[resolved]
        if not agent.is_persistence_enabled():
            agent.enable_persistence()

    if tool_name == "retrieve_memory":
        result = agent.retrieve_for_task(
            task_context=kwargs.get("query", ""),
            user_id=(kwargs.get("user_id") or _default_user_id()),
            task_id=kwargs.get("task_id"),
            platform=kwargs.get("platform") or "hermes",
            project=kwargs.get("project", "default"),
            session_id=kwargs.get("session_id", ""),
            profile=kwargs.get("profile", "default"),
            max_results=kwargs.get("max_results", 5),
            tags=kwargs.get("tags"),
            tags_match_all=bool(kwargs.get("tags_match_all", False)),
            # P1-2 fix (v1.2.14 review): origin hard filters pass through
            # explicit arguments only — transparent by default, like MCP/HTTP.
            origin_platform=kwargs.get("origin_platform"),
            origin_client=kwargs.get("origin_client"),
        )
        # P2.1: core honors max_results; no second slice here.
        working = [
            {"source": m.source, "content": m.content,
             "importance": m.importance, "metadata": m.metadata}
            for m in result.get("retrieved_memories", [])
        ]
        return {
            "working_memory": working,
            "confidence_score": result.get("confidence_score", 0.0),
            "used_weights": agent.rl_optimizer.get_current_weights(),
            "feedback_requested": result.get("feedback_request", False),
        }

    elif tool_name == "store_memory":
        agent.store(
            user_id=(kwargs.get("user_id") or _default_user_id()),
            task_id=kwargs.get("task_id", ""),
            context=kwargs.get("context", []),
            task_status=kwargs.get("task_status", "completed"),
            success=kwargs.get("success", False),
            experience_summary=kwargs.get("experience_summary"),
            platform=kwargs.get("platform") or "hermes",
            title=kwargs.get("title"),
            project=kwargs.get("project", "default"),
            session_id=kwargs.get("session_id", ""),
            profile=kwargs.get("profile", "default"),
            correction=kwargs.get("correction", False),
            tags=kwargs.get("tags"),
            # P1-1/P1-2 fix: this entrypoint IS the Hermes client — mark it
            # explicitly instead of falling back to the transport value.
            origin_client=kwargs.get("origin_client") or "hermes",
        )
        return {"status": "stored",
                "user_id": (kwargs.get("user_id") or _default_user_id()),
                "task_id": kwargs.get("task_id", "")}

    elif tool_name == "record_feedback":
        try:
            agent.record_feedback(
                user_id=(kwargs.get("user_id") or _default_user_id()),
                task_id=kwargs.get("task_id", ""),
                feedback=kwargs.get("feedback", "positive"),
                retrieved_memories=kwargs.get("retrieved_memories", []),
                profile=kwargs.get("profile", "default"),
            )
            return {"status": "feedback_received", "user_id": (kwargs.get("user_id") or _default_user_id())}
        except Exception as e:
            logging.getLogger("MemoryAgent").error("record_feedback failed: %s", e)
            return {"status": "error", "detail": str(e)}

    elif tool_name == "query_memory":
        results = agent.query_memory(
            memory_type=kwargs.get("memory_type", "all"),
            user_id=(kwargs.get("user_id") or _default_user_id()),
            profile=kwargs.get("profile", "default"),
            project=kwargs.get("project"),
            tags=kwargs.get("tags"),
            tags_match_all=bool(kwargs.get("tags_match_all", False)),
            origin_platform=kwargs.get("origin_platform"),
            origin_client=kwargs.get("origin_client"),
            date_from=kwargs.get("date_from"),
            date_to=kwargs.get("date_to"),
            limit=kwargs.get("limit", 20),
        )
        return {"results": results, "count": len(results)}

    elif tool_name == "sync_code_memory":
        agent.sync_to_code_project(
            project_root=kwargs.get("project_root", "."),
            user_id=(kwargs.get("user_id") or _default_user_id()),
        )
        return {"status": "synced",
                "path": f"{kwargs.get('project_root', '.')}/.echomind"}

    elif tool_name == "add_research_paper":
        paper_id = agent.add_research_paper(
            title=kwargs.get("title", ""),
            authors=kwargs.get("authors"),
            year=kwargs.get("year"),
            journal=kwargs.get("journal"),
            abstract=kwargs.get("abstract", ""),
            keywords=kwargs.get("keywords"),
            domain=kwargs.get("domain", "general"),
            paper_type=kwargs.get("paper_type", "theory"),
            key_points=kwargs.get("key_points"),
            importance_score=kwargs.get("importance_score", 0.5),
        )
        return {"status": "stored", "paper_id": paper_id,
                "title": kwargs.get("title", "")}

    elif tool_name == "add_research_note":
        note_id = agent.add_research_note(
            user_id=(kwargs.get("user_id") or _default_user_id()),
            topic=kwargs.get("topic", ""),
            content=kwargs.get("content", ""),
            linked_papers=kwargs.get("linked_papers"),
            tags=kwargs.get("tags"),
        )
        return {"status": "stored", "note_id": note_id,
                "topic": kwargs.get("topic", "")}

    else:
        raise ValueError(f"Unknown tool: {tool_name}")


@atexit.register
def _cleanup_call_agents():
    """Gracefully close all cached agent connections on process exit.

    P2.8 / P0-1 (v1.2.16 audit): delegates to MainMemoryAgent.shutdown() —
    pending reflections are flushed to their recorded owner and the reflection
    thread joined BEFORE disable_persistence() closes the DB, or the
    reflection is deterministically dropped (get_recent_episodic and
    save_reflection are both gated on _persistence_enabled). Previously this
    called _trigger_auto_reflection(platform="hermes") without the required
    user_id, which raised TypeError and was swallowed — every Hermes pending
    reflection was lost at exit.
    """
    for path in list(_call_agents.keys()):
        _evict_call_agent(path)


def init(config_path: str = None):
    """Initialize EchoMind persistence (auto-creates ~/.echomind/memory.db).

    Call once before using call() for the first time in a Python script.
    """
    from core.memory_agent import MainMemoryAgent
    from core.config_manager import get_config_manager
    cfg = get_config_manager(config_path)
    agent = MainMemoryAgent(config_manager=cfg)
    agent.enable_persistence()
    return agent


if "--mcp" in sys.argv:
    print("MCP stdio mode not yet implemented. Use HTTP mode instead.")
    sys.exit(1)
elif __name__ == "__main__":
    from core._reflective_version import get_echomind_version
    from core.config_manager import get_config_manager
    try:
        from adapters.http_api import app, memory_agent
        import uvicorn
    except ImportError as e:
        print(f"Error: Missing HTTP dependency — {e}")
        print("Install with: pip install 'echomind-memory[http]'")
        print("Or: pip install fastapi uvicorn")
        sys.exit(1)

    server_cfg = get_config_manager().get_section("server")
    port = int(sys.argv[1]) if len(sys.argv) > 1 else server_cfg.get("port", 8005)
    host = server_cfg.get("host", "127.0.0.1")

    print("=" * 60)
    print(f"  EchoMind Memory v{get_echomind_version()} — HTTP API Mode")
    print(f"  Endpoint: http://{host}:{port}")
    print(f"  MCP (stdio): python adapters/mcp_gateway.py")
    print(f"  MCP (HTTP):  http://{host}:{port}/mcp   <-- requires HTTP service running")
    print(f"  Docs:       http://{host}:{port}/docs")
    print("=" * 60)
    uvicorn.run(app, host=host, port=port, log_level="info")
else:
    pass