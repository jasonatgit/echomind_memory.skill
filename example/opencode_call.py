"""
OpenCode integration example — via HTTP API
"""
import json
import urllib.request


BASE = "http://localhost:8005"


def post(path: str, data: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return json.loads(urllib.request.urlopen(req, timeout=10).read())


def main():
    print("=== EchoMind Memory × OpenCode ===\n")

    # 1. Retrieve project context
    print("[1] Retrieve context...")
    result = post("/api/memory/retrieve", {
        "user_id": "alice",
        "query": "What is the database design of this project?",
        "task_id": "opencode-project-001",
    })
    print(f"    Confidence: {result.get('confidence_score', 0)}")
    for m in result.get("working_memory", []):
        print(f"    [{m['source']}] {m['content'][:80]}...")

    # 2. Store context
    print("\n[2] Store context...")
    post("/api/memory/store", {
        "user_id": "alice",
        "task_id": "opencode-project-001",
        "context": [
            {"role": "user", "content": "Project database uses PostgreSQL + SQLAlchemy ORM"},
            {"role": "assistant", "content": "recorded. Table structure defined in models.py "},
        ],
        "task_status": "completed",
        "success": True,
    })
    print("    ✅ Stored")

    # 3. Sync code memory
    print("\n[3] Sync to .echomind/...")
    post("/api/memory/sync-code", {
        "project_root": ".",
        "user_id": "alice",
    })
    print("    ✅ Synced (OpenCode will auto-read .echomind/ directory)")

    print("\n=== Completed ===")


if __name__ == "__main__":
    main()