import json
from main import call


def main():
    result = call(
        "retrieve_memory",
        user_id="alice",
        query="How to optimize this function?",
        task_id="task123",
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))

    call(
        "store_memory",
        user_id="alice",
        task_id="task123",
        context=[
            {"role": "user", "content": "How to optimize this function?"},
            {"role": "assistant", "content": "Consider adding exception handling"},
        ],
        task_status="completed",
        success=True,
    )

    call(
        "record_feedback",
        user_id="alice",
        task_id="task123",
        feedback="positive",
        retrieved_memories=result["working_memory"],
    )


main()
