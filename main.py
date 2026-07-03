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

_pkg_dir = os.path.dirname(os.path.abspath(__file__))
if _pkg_dir not in sys.path:
    sys.path.insert(0, _pkg_dir)

# Module-level agent cache: keyed by resolved config_path
_call_agents: dict = {}


def call(tool_name: str, config_path: str = None, **kwargs):
    """Hermes skill.yaml Dispatch entry point

    Supported tools: retrieve_memory, store_memory, record_feedback,
    sync_code_memory, add_research_paper, add_research_note

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
    else:
        agent, cfg = _call_agents[resolved]
        if not agent.is_persistence_enabled():
            agent.enable_persistence()

    if tool_name == "retrieve_memory":
        result = agent.retrieve_for_task(
            task_context=kwargs.get("query", ""),
            user_id=kwargs.get("user_id", ""),
            task_id=kwargs.get("task_id"),
            platform=kwargs.get("platform"),
            profile=kwargs.get("profile", "default"),
        )
        working = [
            {"source": m.source, "content": m.content,
             "importance": m.importance, "metadata": m.metadata}
            for m in result.get("retrieved_memories", [])[:kwargs.get("max_results", 5)]
        ]
        return {
            "working_memory": working,
            "confidence_score": result.get("confidence_score", 0.0),
            "used_weights": agent.rl_optimizer.get_current_weights(),
            "feedback_requested": result.get("feedback_request", False),
        }

    elif tool_name == "store_memory":
        agent.store(
            user_id=kwargs.get("user_id", ""),
            task_id=kwargs.get("task_id", ""),
            context=kwargs.get("context", []),
            task_status=kwargs.get("task_status", "completed"),
            success=kwargs.get("success", False),
            experience_summary=kwargs.get("experience_summary"),
            platform=kwargs.get("platform"),
            project=kwargs.get("project", "default"),
            session_id=kwargs.get("session_id", ""),
            profile=kwargs.get("profile", "default"),
        )
        return {"status": "stored",
                "user_id": kwargs.get("user_id", ""),
                "task_id": kwargs.get("task_id", "")}

    elif tool_name == "record_feedback":
        agent.record_feedback(
            user_id=kwargs.get("user_id", ""),
            task_id=kwargs.get("task_id", ""),
            feedback=kwargs.get("feedback", "positive"),
            retrieved_memories=kwargs.get("retrieved_memories", []),
        )
        return {"status": "feedback_received", "user_id": kwargs.get("user_id", "")}

    elif tool_name == "sync_code_memory":
        agent.sync_to_code_project(
            project_root=kwargs.get("project_root", "."),
            user_id=kwargs.get("user_id", ""),
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
            user_id=kwargs.get("user_id", ""),
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
    """Gracefully close all cached agent connections on process exit."""
    for path, (agent, _) in list(_call_agents.items()):
        try:
            agent.disable_persistence()
        except Exception:
            pass


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