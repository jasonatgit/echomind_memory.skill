import json
import sys
import os
from datetime import datetime, timezone

# Support both direct run and import from core
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.memory_agent import MainMemoryAgent


def main():
    if len(sys.argv) < 4:
        print("Usage: echomind-cli [read|write] <user_id> <project_id> [file_path]")
        sys.exit(1)

    action = sys.argv[1]
    user_id = sys.argv[2]
    project_id = sys.argv[3]
    agent = MainMemoryAgent()
    agent.enable_persistence()

    if action == "read":
        user_mem = agent.user_agent.get(user_id)
        exp_mem = agent.experience_agent.find_similar_tasks(
            task_context=f"code style: {user_mem.get('preferences', {}).get('code_style', 'standard')}",
            task_type="code_review",
            min_success_rate=0.6,
            user_id=user_id,
        )

        result = {
            "user_id": user_id,
            "project_id": project_id,
            "preferences": user_mem.get("preferences", {}),
            "experience": [
                {
                    "action": "fix",
                    "location": "unknown",
                    "summary": m["summary"],
                    "success": m["success"],
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                for m in exp_mem
            ],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif action == "write":
        data = json.load(sys.stdin)
        if "preferences" in data:
            agent.user_agent.update(
                user_id, "preferences", data["preferences"], source="code_cli"
            )
        if "experience" in data:
            for exp in data["experience"]:
                agent.experience_agent.store_experience(
                    user_id=user_id,
                    task_id=f"code_{exp['location']}",
                    task_type="code_review",
                    success=exp["success"],
                    steps=[exp["summary"]],
                    summary=exp["summary"],
                )
        print(json.dumps({"status": "written"}))

    agent.disable_persistence()


if __name__ == "__main__":
    main()