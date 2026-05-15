"""
OpenClaw integration example — using call() from main.py

    from echomind_memory.main import call
    result = call("retrieve_memory", user_id="alice", query="...")
"""
import json
from main import call


def main():
    print("=== EchoMind Memory × OpenClaw ===\n")

    # 1. Retrieve memory
    print("[1] Retrieve memory...")
    result = call(
        "retrieve_memory",
        user_id="alice",
        query="How to optimize database query performance?",
        task_id="task-openclaw-001",
    )
    print(f"    Confidence: {result.get('confidence_score', 0)}")
    print(f"    Memory source: {[m['source'] for m in result.get('working_memory', [])]}")
    for m in result.get("working_memory", []):
        print(f"      [{m['source']}] {m['content'][:60]}...")

    # 2. Store interaction result
    print("\n[2] Store interaction...")
    call(
        "store_memory",
        user_id="alice",
        task_id="task-openclaw-001",
        context=[
            {"role": "user", "content": "How to optimize database query performance?"},
            {"role": "assistant", "content": "Consider adding indexes and enabling query cache."},
        ],
        task_status="completed",
        success=True,
        experience_summary="Optimized query performance by adding indexes and cache",
    )
    print("    ✅ Stored")

    # 3. Add research paper
    print("\n[3] Add paper...")
    call(
        "add_research_paper",
        title="Query Optimization in Large-Scale Databases",
        authors=["Chen X", "Liu Y"],
        year=2024,
        abstract="Discusses indexing and caching strategies...",
        keywords=["database", "optimization", "indexing"],
        domain="computer_science",
    )
    print("    ✅ Paper added")

    # 4. Record feedback
    print("\n[4] Record feedback...")
    call(
        "record_feedback",
        user_id="alice",
        task_id="task-openclaw-001",
        feedback="positive",
        retrieved_memories=[],
    )
    print("    ✅ Feedback recorded (RL Weights updated)")

    print("\n=== Completed ===")


if __name__ == "__main__":
    main()