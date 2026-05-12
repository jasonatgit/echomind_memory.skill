from main import call, init


def main():
    init()

    call(
        "sync_code_memory",
        project_root="/Users/alice/my-python-project",
        user_id="alice",
    )
    print("已同步到 .echomind/，请在 Cursor 中查看")


if __name__ == "__main__":
    main()