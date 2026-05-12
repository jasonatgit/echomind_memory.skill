"""
OpenClaw 集成示例

OpenClaw 框架通过 skill.yaml 自动发现工具，然后调用 main.call(tool_name, **kwargs)。
无需额外配置，将本技能放入 OpenClaw 的 skills/ 目录下即可。
"""

from main import call, init
from models.research import ResearchPaper, ResearchNote


def main():
    # 初始化持久化
    init()

    # ========================
    # 1. 检索记忆
    # ========================
    print("=== 检索记忆 ===")
    result = call(
        "retrieve_memory",
        user_id="alice",
        query="供应链协调契约机制有哪些？",
    )
    for m in result["working_memory"]:
        print(f"  [{m['source']}] {m['content'][:80]}")

    # ========================
    # 2. 存储记忆
    # ========================
    print("\n=== 存储记忆 ===")
    result = call(
        "store_memory",
        user_id="alice",
        task_id="sc-task-001",
        context=[
            {"role": "user", "content": "供应链协调契约机制有哪些？"},
            {"role": "assistant", "content": "常见的有收入共享契约、回购契约等"},
        ],
        task_status="completed",
        success=True,
        experience_summary="用户对供应链契约感兴趣，偏好收入共享模型",
    )
    print(result)

    # ========================
    # 3. 记录反馈
    # ========================
    print("\n=== 记录反馈 ===")
    result = call(
        "record_feedback",
        user_id="alice",
        task_id="sc-task-001",
        feedback="positive",
        retrieved_memories=[],
    )
    print(result)

    # ========================
    # 4. 添加研究论文（直接使用 agent）
    # ========================
    from main import memory_agent

    print("\n=== 添加研究论文 ===")
    memory_agent.research_agent.add_paper(ResearchPaper(
        title="Supply Chain Coordination with Contracts",
        authors=["Tsay", "Nahmias", "Agrawal"],
        domain="supply_chain",
        paper_type="review",
        key_points=["Contracts align incentives in decentralized supply chains"],
        importance_score=0.85,
    ))
    print("论文已添加，下次检索供应链相关问题时将自动匹配")


if __name__ == "__main__":
    main()