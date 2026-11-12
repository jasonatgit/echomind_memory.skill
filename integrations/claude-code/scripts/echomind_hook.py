#!/usr/bin/env python3
"""Claude Code lifecycle hook → EchoMind memory endpoint.

All five plugin events (SessionStart, UserPromptSubmit, Stop, PreCompact,
SessionEnd) run through this one stdlib script: it reads the event JSON from
stdin and POSTs it to EchoMind's /api/hooks/claude, printing the hook JSON
Claude reads.

Environment:
  ECHOMIND_URL        base URL (default http://127.0.0.1:8005)
  ECHOMIND_API_KEY    optional X-API-Key
  ECHOMIND_HOOK_USER / ECHOMIND_HOOK_PROFILE / ECHOMIND_HOOK_PROJECT  optional

Always prints a JSON object and exits 0; waits are capped at 3 s for recall and
10 s for store events, so a down or slow service cannot fail the turn.
"""

import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_URL = "http://127.0.0.1:8005"


def _read_stdin_json() -> dict:
    try:
        # Claude writes UTF-8 JSON; do not let the Windows console code page
        # decode it (cp936/cp1252 would mojibake non-ASCII prompts).
        buffer = getattr(sys.stdin, "buffer", None)
        raw = (buffer.read().decode("utf-8", "replace")
               if buffer is not None else sys.stdin.read())
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

    # The hook payload does not carry identity overrides; forward this
    # process's environment explicitly.
    for field, env in (("user_id", "ECHOMIND_HOOK_USER"),
                       ("profile", "ECHOMIND_HOOK_PROFILE"),
                       ("project", "ECHOMIND_HOOK_PROJECT")):
        if not payload.get(field):
            value = os.environ.get(env, "").strip()
            if value:
                payload[field] = value

    base = (os.environ.get("ECHOMIND_URL") or DEFAULT_URL).rstrip("/")
    url = f"{base}/api/hooks/claude"
    headers = {"Content-Type": "application/json"}
    api_key = os.environ.get("ECHOMIND_API_KEY", "")
    if api_key:
        headers["X-API-Key"] = api_key

    # Recall must not stall the prompt; store events may take a little longer.
    event = str(payload.get("hook_event_name") or "")
    timeout = 3 if event in ("SessionStart", "UserPromptSubmit") else 10

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace").strip()
        # Pass through only a JSON object; anything else becomes a no-op.
        parsed = json.loads(body) if body else {}
        out = parsed if isinstance(parsed, dict) else {}
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, OSError):
        out = {}

    # ensure_ascii keeps the output encodable on any console; Claude parses the
    # JSON and recovers the original text.
    sys.stdout.write(json.dumps(out))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
