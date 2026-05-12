from main import call
import asyncio


async def main():
    await call(
        "sync_code_memory",
        project_root="/Users/alice/my-python-project",
        user_id="alice",
    )
    print("✅ 已同步到 .echomind/，请在 Cursor 中查看")


asyncio.run(main())
