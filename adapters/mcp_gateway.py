#!/usr/bin/env python3
"""EchoMind MCP Server (thin stdio gateway) — delegates to mcp_common.py.

Claude Code MCP protocol over stdio. All tool/API/dispatch logic lives in
mcp_common.py. This file provides only the stdio IO loop and env config.
"""
import json
import os
import sys

# Ensure adapters package is importable when running as standalone script
_pkg_dir = os.path.dirname(os.path.abspath(__file__))
if _pkg_dir not in sys.path:
    sys.path.insert(0, os.path.dirname(_pkg_dir))
from adapters.mcp_common import handle_mcp_request

# Support both env var names for backward compatibility
_API_KEY = os.environ.get("ECHOMIND_API_KEY", "") or os.environ.get("ECHOMIND_API_TOKEN", "")

# Override mcp_common's API key check at module level
import adapters.mcp_common as _mc
_mc._API_KEY = _API_KEY


def main():
    """Read JSON-RPC requests from stdin, write responses to stdout."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = handle_mcp_request(msg)
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()