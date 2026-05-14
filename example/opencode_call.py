"""
OpenCode 集成示例 — 通过 CLI 工具调用 EchoMind Memory

使用方式:
    python3 code_format/cli.py read <user_id> <project_id>
    python3 code_format/cli.py write <user_id> <project_id> <file_path>

或直接通过 FastAPI 调用:
    curl -X POST http://localhost:8005/api/memory/retrieve \
      -H "Content-Type: application/json" \
      -d '{"user_id": "alice", "query": "查找项目相关上下文"}'
"""

import asyncio
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

    # 1. 检索项目上下文
    print("[1] 检索上下文...")
    result = post("/api/memory/retrieve", {
        "user_id": "alice",
        "query": "这个项目的数据库设计是怎样的？",
        "task_id": "opencode-project-001",
    })
    print(f"    置信度: {result.get('confidence_score', 0)}")
    for m in result.get("working_memory", []):
        print(f"    [{m['source']}] {m['content'][:80]}...")

    # 2. 存储上下文
    print("\n[2] 存储上下文...")
    post("/api/memory/store", {
        "user_id": "alice",
        "task_id": "opencode-project-001",
        "context": [
            {"role": "user", "content": "项目数据库使用 PostgreSQL + SQLAlchemy ORM"},
            {"role": "assistant", "content": "已记录。表结构在 models.py 中定义。"},
        ],
        "task_status": "completed",
        "success": True,
    })
    print("    ✅ 已存储")

    # 3. 同步代码记忆
    print("\n[3] 同步到 .echomind/...")
    post("/api/memory/sync-code", {
        "project_root": ".",
        "user_id": "alice",
    })
    print("    ✅ 已同步 (OpenCode 将自动读取 .echomind/ 目录)")

    print("\n=== 完成 ===")


if __name__ == "__main__":
    main()