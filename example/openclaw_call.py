"""
OpenClaw 集成示例 — 通过 skill.yaml 定义的 MCP tool 调用 EchoMind Memory

使用方式:
    from echomind_memory.main import call

    result = await call("retrieve_memory", user_id="alice", query="...")
"""

import asyncio
import json
from main import call


async def main():
    print("=== EchoMind Memory × OpenClaw ===\n")

    # 1. 检索记忆
    print("[1] 检索记忆...")
    result = await call(
        "retrieve_memory",
        user_id="alice",
        query="如何优化数据库查询性能？",
        task_id="task-openclaw-001",
    )
    print(f"    置信度: {result.get('confidence_score', 0)}")
    print(f"    记忆来源: {[m['source'] for m in result.get('working_memory', [])]}")
    for m in result.get("working_memory", []):
        print(f"      [{m['source']}] {m['content'][:60]}...")

    # 2. 存储交互结果
    print("\n[2] 存储交互...")
    await call(
        "store_memory",
        user_id="alice",
        task_id="task-openclaw-001",
        context=[
            {"role": "user", "content": "如何优化数据库查询性能？"},
            {"role": "assistant", "content": "建议添加索引并启用查询缓存。"},
        ],
        task_status="completed",
        success=True,
        experience_summary="通过添加索引和缓存优化了查询性能",
    )
    print("    ✅ 已存储")

    # 3. 添加研究论文
    print("\n[3] 添加论文...")
    await call(
        "add_research_paper",
        title="Query Optimization in Large-Scale Databases",
        authors=["Chen X", "Liu Y"],
        year=2024,
        abstract="Discusses indexing and caching strategies...",
        keywords=["database", "optimization", "indexing"],
        domain="computer_science",
    )
    print("    ✅ 论文已添加")

    # 4. 记录反馈
    print("\n[4] 记录反馈...")
    await call(
        "record_feedback",
        user_id="alice",
        task_id="task-openclaw-001",
        feedback="positive",
        retrieved_memories=[],
    )
    print("    ✅ 反馈已记录 (RL 权重已更新)")

    print("\n=== 完成 ===")


if __name__ == "__main__":
    asyncio.run(main())