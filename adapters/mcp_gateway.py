#!/usr/bin/env python3
"""EchoMind MCP Server (thin stdio gateway) — delegates to mcp_common.py.

Claude Code MCP protocol over stdio. All tool/API logic lives in mcp_common.py.
This file provides only the stdio main loop and environment configuration.
"""
import json
import os
import sys

# Ensure adapters package is importable when running as standalone script
_pkg_dir = os.path.dirname(os.path.abspath(__file__))
if _pkg_dir not in sys.path:
    sys.path.insert(0, os.path.dirname(_pkg_dir))
from adapters.mcp_common import (
    handle_mcp_request, handle_tools_list, handle_resources_list,
    handle_resource_read, handle_tool_call,
)

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
        # Handle MCP initialize handshake
        if msg.get("method") == "initialize":
            response = {
                "jsonrpc": "2.0",
                "id": msg.get("id"),
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {},
                        "resources": {},
                    },
                    "serverInfo": {"name": "echomind-mcp", "version": "1.0.0"},
                },
            }
        elif msg.get("method") == "notifications/initialized":
            continue
        elif msg.get("method") == "tools/list":
            response = {"jsonrpc": "2.0", "id": msg.get("id"), "result": handle_tools_list()}
        elif msg.get("method") == "resources/list":
            response = {"jsonrpc": "2.0", "id": msg.get("id"), "result": handle_resources_list()}
        elif msg.get("method") == "resources/read":
            params = msg.get("params", {})
            uri = params.get("uri", "")
            response = {"jsonrpc": "2.0", "id": msg.get("id"), "result": handle_resource_read(uri)}
        elif msg.get("method") == "tools/call":
            params = msg.get("params", {})
            name = params.get("name", "")
            arguments = params.get("arguments", {})
            result = handle_tool_call(name, arguments)
            content = result.get("content", [])
            is_error = "error" in result
            response = {
                "jsonrpc": "2.0",
                "id": msg.get("id"),
                "result": {"content": content},
            }
            if is_error:
                response["isError"] = True
        else:
            response = {
                "jsonrpc": "2.0",
                "id": msg.get("id"),
                "error": {"code": -32601, "message": f"Method not found: {msg.get('method')}"},
            }
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()