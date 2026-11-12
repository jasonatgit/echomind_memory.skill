#!/usr/bin/env python3
"""Claude Code SessionStart hook → EchoMind memory briefing.

Claude Code only supports command/mcp_tool hooks on SessionStart, and MCP
tools are unavailable at launch, so this tiny stdlib script bridges the event
to EchoMind's HTTP hook endpoint and prints the hook JSON Claude reads.

Environment:
  ECHOMIND_URL        base URL (default http://127.0.0.1:8005)
  ECHOMIND_API_KEY    optional X-API-Key
  ECHOMIND_HOOK_USER / ECHOMIND_HOOK_PROFILE / ECHOMIND_HOOK_PROJECT  optional

Always prints a JSON object; on any failure it prints {} so the session is
never blocked by a memory outage.
"""

import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_URL = "http://127.0.0.1:8005"


def _read_stdin_json() -> dict:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return {}
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def main() -> int:
    payload = _read_stdin_json()
    # Fallback event name from argv (Claude passes it in the payload too).
    if len(sys.argv) > 1 and not payload.get("hook_event_name"):
        payload["hook_event_name"] = sys.argv[1]

    base = (os.environ.get("ECHOMIND_URL") or DEFAULT_URL).rstrip("/")
    url = f"{base}/api/hooks/claude"
    headers = {"Content-Type": "application/json"}
    api_key = os.environ.get("ECHOMIND_API_KEY", "")
    if api_key:
        headers["X-API-Key"] = api_key

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", "replace").strip()
        # Pass through only a JSON object; anything else becomes a no-op.
        parsed = json.loads(body) if body else {}
        out = parsed if isinstance(parsed, dict) else {}
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, OSError):
        out = {}

    sys.stdout.write(json.dumps(out, ensure_ascii=False))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
