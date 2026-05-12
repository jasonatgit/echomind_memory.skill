"""
OpenCode 集成示例

OpenCode 生态通过 CLI 或 JSON Schema 标准化格式获取记忆。
本示例展示两种使用方式：
  1. Python API: 直接 call() 函数
  2. CLI: python -m example.opencode_call <user_id> <query>
"""

import json
import sys
from main import call, init


def api_example():
    """通过 Python API 使用（推荐给 OpenCode Agent 框架）"""
    init()

    # 检索
    result = call(
        "retrieve_memory",
        user_id="alice",
        query="运筹学优化模型有哪些",
    )

    # 输出标准化 JSON，可直接注入 LLM prompt
    output = {
        "context": "\n".join(m["content"] for m in result["working_memory"]),
        "confidence": result["confidence_score"],
        "sources": [m["source"] for m in result["working_memory"]],
    }
    return output


def cli_example():
    """CLI 调用方式"""
    if len(sys.argv) < 3:
        print("用法: python -m example.opencode_call <user_id> <query>", file=sys.stderr)
        sys.exit(1)

    user_id = sys.argv[1]
    query = " ".join(sys.argv[2:])
    sys.stdout.reconfigure(encoding="utf-8")

    init()
    result = call("retrieve_memory", user_id=user_id, query=query)

    # 输出纯 JSON 供 OpenCode 解析
    print(json.dumps({
        "working_memory": result["working_memory"],
        "confidence_score": result["confidence_score"],
        "feedback_requested": result["feedback_requested"],
    }, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cli_example()
    else:
        output = api_example()
        print(json.dumps(output, indent=2, ensure_ascii=False))
        print("\n--- 可注入 LLM 的上下文 ---")
        print(output["context"])