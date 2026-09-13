import json
import sys
import os
from datetime import datetime, timezone

# Support both direct run and import from core
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.memory_agent import MainMemoryAgent

ACTIONS = ("read", "write")
_EXPERIENCE_KEYS = ("location", "success", "summary")


def _usage():
    print("Usage: echomind-cli [read|write] <user_id> <project_id> [file_path]")


def _read(agent, user_id, project_id):
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


def _write(agent, user_id):
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"error: invalid JSON on stdin: {e}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(data, dict):
        print("error: stdin JSON must be an object with 'preferences'/'experience'",
              file=sys.stderr)
        sys.exit(1)
    if "preferences" in data:
        agent.user_agent.update(
            user_id, "preferences", data["preferences"], source="code_cli"
        )
    if "experience" in data:
        if not isinstance(data["experience"], list):
            print("error: 'experience' must be a list", file=sys.stderr)
            sys.exit(1)
        for exp in data["experience"]:
            if not isinstance(exp, dict) or any(k not in exp for k in _EXPERIENCE_KEYS):
                missing = [k for k in _EXPERIENCE_KEYS
                           if not isinstance(exp, dict) or k not in exp]
                print(f"error: experience entry missing keys {missing}: {exp!r}",
                      file=sys.stderr)
                sys.exit(1)
            agent.experience_agent.store_experience(
                user_id=user_id,
                task_id=f"code_{exp['location']}",
                task_type="code_review",
                success=exp["success"],
                steps=[exp["summary"]],
                summary=exp["summary"],
            )
    print(json.dumps({"status": "written"}))


def main():
    if len(sys.argv) < 4:
        _usage()
        sys.exit(1)

    action = sys.argv[1]
    user_id = sys.argv[2]
    project_id = sys.argv[3]
    if action not in ACTIONS:
        print(f"error: unknown action '{action}' (expected one of {', '.join(ACTIONS)})",
              file=sys.stderr)
        _usage()
        sys.exit(1)

    # P3.6: try/finally so an error mid-run still closes the DB connection
    # (the old form leaked the connection and skipped the WAL checkpoint).
    agent = MainMemoryAgent()
    try:
        agent.enable_persistence()
        if action == "read":
            _read(agent, user_id, project_id)
        else:
            _write(agent, user_id)
    finally:
        try:
            agent.disable_persistence()
        except Exception:
            pass


if __name__ == "__main__":
    main()
