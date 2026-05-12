# echomind_memory.skill/main.py

import json
import os
from typing import Any, Dict, List
from memory_agent import MainMemoryAgent


memory_agent = MainMemoryAgent()


def init():
    memory_agent.enable_persistence()


def retrieve_memory(
    user_id: str, query: str, task_id: str = None, max_results: int = 5
) -> Dict[str, Any]:
    try:
        result = memory_agent.retrieve_for_task(query, user_id, task_id)
        confidence = sum(m.importance for m in result["working_memory"]) / (
            len(result["working_memory"]) or 1
        )
        return {
            "working_memory": [
                {
                    "source": m.source,
                    "content": m.content,
                    "importance": m.importance,
                    "metadata": m.metadata,
                }
                for m in result["working_memory"][:max_results]
            ],
            "confidence_score": float(confidence),
            "used_weights": memory_agent.rl_optimizer.get_current_weights(),
            "feedback_requested": result.get("feedback_request", False),
        }
    except Exception as e:
        return {
            "working_memory": [],
            "confidence_score": 0.0,
            "used_weights": memory_agent.rl_optimizer.get_current_weights(),
            "feedback_requested": False,
            "error": str(e),
        }


def store_memory(
    user_id: str,
    task_id: str,
    context: List[Dict],
    task_status: str,
    success: bool = False,
    experience_summary: str = None,
) -> Dict[str, Any]:
    try:
        memory_agent.store(
            user_id, task_id, context, task_status, success, experience_summary
        )
        return {"status": "stored", "user_id": user_id, "task_id": task_id}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def record_feedback(
    user_id: str, task_id: str, feedback: str, retrieved_memories: List[Dict]
) -> Dict[str, Any]:
    try:
        memory_agent.record_feedback(user_id, task_id, feedback, retrieved_memories)
        return {"status": "feedback_received", "user_id": user_id, "feedback": feedback}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def sync_code_memory(project_root: str, user_id: str) -> Dict[str, Any]:
    try:
        memory_agent.sync_to_code_project(project_root, user_id)
        return {"status": "synced", "path": f"{project_root}/.echomind"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def call(tool_name: str, **kwargs) -> Dict[str, Any]:
    if tool_name == "retrieve_memory":
        return retrieve_memory(**kwargs)
    elif tool_name == "store_memory":
        return store_memory(**kwargs)
    elif tool_name == "record_feedback":
        return record_feedback(**kwargs)
    elif tool_name == "sync_code_memory":
        return sync_code_memory(**kwargs)
    else:
        return {"error": f"Unknown tool: {tool_name}"}


if __name__ == "__main__":
    result = call("retrieve_memory", user_id="testuser", query="写一个Python函数")
    print(json.dumps(result, indent=2, ensure_ascii=False))