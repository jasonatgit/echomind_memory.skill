import json
from main import call, init


def main():
    # 初始化 SQLite 持久化
    init()

    result = call(
        "retrieve_memory",
        user_id="alice",
        query="这个函数怎么优化？",
        task_id="task123",
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))

    call(
        "store_memory",
        user_id="alice",
        task_id="task123",
        context=[
            {"role": "user", "content": "这个函数怎么优化？"},
            {"role": "assistant", "content": "建议加入异常处理"},
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


if __name__ == "__main__":
    main()