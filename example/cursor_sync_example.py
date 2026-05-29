from main import call


def main():
    call(
        "sync_code_memory",
        project_root="/Users/alice/my-python-project",
        user_id="alice",
    )
    print("Synced to .echomind/")


main()
