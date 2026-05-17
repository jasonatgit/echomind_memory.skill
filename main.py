#!/usr/bin/env python3
# EchoMind Memory — 统一入口
# 
# HTTP 模式 (默认): python3 main.py
#   启动 FastAPI 服务，供 OpenClaw / OpenCode / Claude Code 通过 HTTP 调用
#
# OpenClaw call() 模式: from main import call
#   直接调用工具函数，供 OpenClaw skill.yaml 调度
#
# MCP 模式: python3 main.py --mcp  
#   启动 MCP stdio 服务（未来实现）

import sys
import os

# 确保项目根目录在 sys.path
_pkg_dir = os.path.dirname(os.path.abspath(__file__))
if _pkg_dir not in sys.path:
    sys.path.insert(0, _pkg_dir)


def call(tool_name: str, **kwargs):
    """OpenClaw skill.yaml 调度入口
    
    将 skill.yaml 工具名称映射为 HTTP API 调用。
    支持的工具：retrieve_memory, store_memory, record_feedback,
    sync_code_memory, add_research_paper, add_research_note
    
    用法：
        from main import call
        result = call("retrieve_memory", user_id="alice", query="...")
    """
    from core.memory_agent import MainMemoryAgent
    agent = MainMemoryAgent()
    agent.enable_persistence()

    try:
        if tool_name == "retrieve_memory":
            result = agent.retrieve_for_task(
                task_context=kwargs.get("query", ""),
                user_id=kwargs.get("user_id", ""),
                task_id=kwargs.get("task_id"),
                platform=kwargs.get("platform"),
            )
            working = [
                {"source": m.source, "content": m.content,
                 "importance": m.importance, "metadata": m.metadata}
                for m in result.get("retrieved_memories", [])[:kwargs.get("max_results", 5)]
            ]
            confidence = sum(m.importance for m in result.get("retrieved_memories", [])) \
                / max(len(result.get("retrieved_memories", [])), 1)
            return {
                "working_memory": working,
                "confidence_score": float(confidence),
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
            )
            return {"status": "stored",
                    "user_id": kwargs["user_id"],
                    "task_id": kwargs["task_id"]}

        elif tool_name == "record_feedback":
            agent.record_feedback(
                user_id=kwargs.get("user_id", ""),
                task_id=kwargs.get("task_id", ""),
                feedback=kwargs.get("feedback", "positive"),
                retrieved_memories=kwargs.get("retrieved_memories", []),
            )
            return {"status": "feedback_received", "user_id": kwargs["user_id"]}

        elif tool_name == "sync_code_memory":
            agent.sync_to_code_project(
                project_root=kwargs.get("project_root", "."),
                user_id=kwargs.get("user_id", ""),
            )
            return {"status": "synced",
                    "path": f"{kwargs['project_root']}/.echomind"}

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
                    "title": kwargs["title"]}

        elif tool_name == "add_research_note":
            note_id = agent.add_research_note(
                user_id=kwargs.get("user_id", ""),
                topic=kwargs.get("topic", ""),
                content=kwargs.get("content", ""),
                linked_papers=kwargs.get("linked_papers"),
                tags=kwargs.get("tags"),
            )
            return {"status": "stored", "note_id": note_id,
                    "topic": kwargs["topic"]}

        else:
            raise ValueError(f"Unknown tool: {tool_name}")

    finally:
        agent.disable_persistence()


if "--mcp" in sys.argv:
    # TODO: MCP stdio 模式（未来实现）
    print("MCP stdio mode not yet implemented. Use HTTP mode instead.")
    sys.exit(1)
elif __name__ == "__main__":
    # HTTP API 模式 — 向后兼容
    from adapters.http_api import app, memory_agent
    import uvicorn

    print("=" * 60)
    print("  EchoMind Memory v1.0.8 — HTTP API Mode")
    print("  Endpoint: http://localhost:8005")
    print("  Docs:     http://localhost:8005/docs")
    print("=" * 60)
    memory_agent.enable_persistence()
    uvicorn.run(app, host="0.0.0.0", port=8005, log_level="info")
else:
    # 作为模块导入时：暴露 call() 函数供 OpenClaw 使用
    # from main import call
    pass