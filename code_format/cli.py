import json
import sys
import os
from datetime import datetime, timezone

# Support both direct run and import from core
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.memory_agent import MainMemoryAgent

ACTIONS = ("read", "write", "query")
_EXPERIENCE_KEYS = ("location", "success", "summary")


def _usage():
    print("Usage: echomind-cli [read|write] <user_id> <project_id> [file_path]")
    print("       echomind-cli query <user_id> [project_id] [--tags a,b] [--tags-all]")
    print("                          [--origin-client c] [--origin-platform p] [--profile p]")
    print("                          [--type t] [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--limit n]")


def _read(agent, user_id, project_id):
    user_mem = agent.user_agent.get(user_id)
    exp_mem = agent.experience_agent.find_similar_tasks(
        task_context=f"code style: {user_mem.get('preferences', {}).get('code_style', 'standard')}",
        task_type="code_review",
        min_success_rate=0.6,
        user_id=user_id,
    )

    result = {
        "user_id": user_id,
        "project_id": project_id,
        "preferences": user_mem.get("preferences", {}),
        "experience": [
            {
                "action": "fix",
                "location": "unknown",
                "summary": m["summary"],
                "success": m["success"],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            for m in exp_mem
        ],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))


def _write(agent, user_id):
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"error: invalid JSON on stdin: {e}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(data, dict):
        print("error: stdin JSON must be an object with 'preferences'/'experience'",
              file=sys.stderr)
        sys.exit(1)
    if "preferences" in data:
        agent.user_agent.update(
            user_id, "preferences", data["preferences"], source="code_cli"
        )
    if "experience" in data:
        if not isinstance(data["experience"], list):
            print("error: 'experience' must be a list", file=sys.stderr)
            sys.exit(1)
        for exp in data["experience"]:
            if not isinstance(exp, dict) or any(k not in exp for k in _EXPERIENCE_KEYS):
                missing = [k for k in _EXPERIENCE_KEYS
                           if not isinstance(exp, dict) or k not in exp]
                print(f"error: experience entry missing keys {missing}: {exp!r}",
                      file=sys.stderr)
                sys.exit(1)
            agent.experience_agent.store_experience(
                user_id=user_id,
                task_id=f"code_{exp['location']}",
                task_type="code_review",
                success=exp["success"],
                steps=[exp["summary"]],
                summary=exp["summary"],
            )
    print(json.dumps({"status": "written"}))


def _query(agent, argv):
    """Structured provenance query (v1.2.14): --project --tags --tags-all
    --origin-client --origin-platform --type --from --to --limit."""
    # Positional args stop at the first --option so unknown options are
    # rejected below instead of being consumed as the project id.
    positional = []
    idx = 0
    while idx < len(argv) and not argv[idx].startswith("--"):
        positional.append(argv[idx])
        idx += 1
    if not positional:
        print("error: query requires <user_id>", file=sys.stderr)
        sys.exit(1)
    opts = {"user_id": positional[0],
            "project": positional[1] if len(positional) > 1 else None,
            "memory_type": "all", "tags": None, "tags_match_all": False,
            "profile": "default",
            "origin_client": None, "origin_platform": None,
            "date_from": None, "date_to": None, "limit": 20}
    i = idx
    while i < len(argv):
        key = argv[i]
        if key == "--tags" and i + 1 < len(argv):
            opts["tags"] = [t for t in argv[i + 1].split(",") if t.strip()]
            i += 2
        elif key == "--tags-all":
            opts["tags_match_all"] = True
            i += 1
        elif key in ("--origin-client", "--origin-platform", "--type",
                     "--profile", "--from", "--to", "--limit") and i + 1 < len(argv):
            opts[{"--origin-client": "origin_client",
                  "--origin-platform": "origin_platform",
                  "--type": "memory_type",
                  "--profile": "profile",
                  "--from": "date_from",
                  "--to": "date_to",
                  "--limit": "limit"}[key]] = argv[i + 1]
            i += 2
        else:
            print(f"error: unknown option '{key}'", file=sys.stderr)
            sys.exit(1)
    results = agent.query_memory(
        memory_type=opts["memory_type"], user_id=opts["user_id"],
        profile=opts["profile"],
        project=opts["project"], tags=opts["tags"],
        tags_match_all=opts["tags_match_all"],
        origin_platform=opts["origin_platform"],
        origin_client=opts["origin_client"],
        date_from=opts["date_from"], date_to=opts["date_to"],
        limit=int(opts["limit"]),
    )
    from core.provenance import format_origin_line
    print(json.dumps({"count": len(results), "results": [
        {**r, "origin_line": format_origin_line(r.get("envelope"), r.get("created_at", ""))}
        for r in results
    ]}, indent=2, ensure_ascii=False, default=str))


def main():
    action = sys.argv[1]
    if action not in ACTIONS:
        print(f"error: unknown action '{action}' (expected one of {', '.join(ACTIONS)})",
              file=sys.stderr)
        _usage()
        sys.exit(1)

    # P2-2 fix (v1.2.14 review): query takes <user_id> plus options — it must
    # not be gated behind the read/write 3-argument requirement.
    if action == "query":
        if len(sys.argv) < 3:
            print("error: query requires <user_id>", file=sys.stderr)
            sys.exit(1)
        agent = MainMemoryAgent()
        try:
            agent.enable_persistence()
            _query(agent, sys.argv[2:])
        finally:
            try:
                agent.disable_persistence()
            except Exception:
                pass
        return

    if len(sys.argv) < 4:
        _usage()
        sys.exit(1)

    user_id = sys.argv[2]
    project_id = sys.argv[3]

    # P3.6: try/finally so an error mid-run still closes the DB connection
    # (the old form leaked the connection and skipped the WAL checkpoint).
    agent = MainMemoryAgent()
    try:
        agent.enable_persistence()
        if action == "read":
            _read(agent, user_id, project_id)
        else:
            _write(agent, user_id)
    finally:
        try:
            agent.disable_persistence()
        except Exception:
            pass


if __name__ == "__main__":
    main()
