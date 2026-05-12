import json
import asyncio
from main import call


async def main():
    result = await call(
        "retrieve_memory",
        user_id="alice",
        query="这个函数怎么优化？",
        task_id="task123",
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))

    await call(
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

    await call(
        "record_feedback",
        user_id="alice",
        task_id="task123",
        feedback="positive",
        retrieved_memories=result["working_memory"],
    )


asyncio.run(main())
