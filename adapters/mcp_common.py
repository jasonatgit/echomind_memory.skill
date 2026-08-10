"""Shared MCP tool handlers used by both stdio gateway and HTTP MCP endpoint.

Purpose: eliminate code duplication between mcp_gateway.py (stdio) and
http_api.py (Streamable HTTP MCP). Both import handle_tools_list,
handle_tool_call, handle_resources_list, handle_resource_read, and
handle_mcp_request from this module.
"""

import json
import os
import urllib.request
import urllib.error

ECHOMIND_URL = "http://127.0.0.1:8005"
_API_KEY = os.environ.get("ECHOMIND_API_KEY", "") or os.environ.get("ECHOMIND_API_TOKEN", "")


def _headers(extra=None) -> dict:
    h = {"Content-Type": "application/json"}
    if _API_KEY:
        h["X-API-Key"] = _API_KEY
    if extra:
        h.update(extra)
    return h


def _api_post(path, body):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{ECHOMIND_URL}{path}", data=data,
        headers=_headers(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')}"}
    except Exception as e:
        return {"error": str(e)}


def _api_get(path):
    req = urllib.request.Request(f"{ECHOMIND_URL}{path}", headers=_headers(), method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}"}
    except Exception as e:
        return {"error": str(e)}


def _api_delete(path):
    req = urllib.request.Request(f"{ECHOMIND_URL}{path}", headers=_headers(), method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}"}
    except Exception as e:
        return {"error": str(e)}


# ── Tool & Resource definitions ─────────────────────────

def handle_tools_list():
    return {"tools": [
        {
            "name": "echomind_retrieve",
            "description": "Search EchoMind long-term memory for relevant context.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "user_id": {"type": "string", "default": "cli"},
                    "max_results": {"type": "integer", "default": 5},
                    "project": {"type": "string", "default": "default"},
                    "session_id": {"type": "string", "default": ""},
                    "profile": {"type": "string", "default": "default"},
                },
                "required": ["query"],
            },
        },
        {
            "name": "echomind_store",
            "description": "Store interaction result into EchoMind long-term memory.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "default": "cli"},
                    "task_id": {"type": "string", "default": ""},
                    "task_status": {"type": "string", "default": "completed"},
                    "success": {"type": "boolean", "default": True},
                    "experience_summary": {"type": "string"},
                    "context": {"type": "array", "items": {"type": "object"}},
                    "project": {"type": "string", "default": "default"},
                    "session_id": {"type": "string", "default": ""},
                    "profile": {"type": "string", "default": "default"},
                },
                "required": [],
            },
        },
        {
            "name": "echomind_search",
            "description": "Search session transcripts by keyword.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "user_id": {"type": "string", "default": ""},
                    "limit": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        },
        {
            "name": "echomind_feedback",
            "description": "Provide feedback on a retrieval result.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "task_id": {"type": "string"},
                    "feedback": {"type": "string", "enum": ["positive", "negative"]},
                    "memory_ids": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["user_id", "task_id", "feedback"],
            },
        },
        {
            "name": "echomind_reflect",
            "description": "Trigger reflection on recent memories. Phase 1 (no llm_response) returns a prompt for caller-side LLM processing; Phase 2 (with llm_response) commits the reflection result to memory.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "count": {"type": "integer", "default": 8},
                    "llm_response": {"type": "string", "description": "Optional. LLM response to the Phase-1 prompt. Omit for Phase 1 (build prompt)."},
                    "record_ids": {"type": "array", "items": {"type": "string"}, "description": "Optional. Specific record IDs to reflect on (Phase 2)."},
                    "platform": {"type": "string", "default": "http"},
                    "profile": {"type": "string", "default": "default"},
                },
                "required": ["user_id"],
            },
        },
        {
            "name": "echomind_delete",
            "description": "Delete a specific memory entry by type and ID.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "memory_type": {"type": "string", "enum": [
                        "user", "task", "experience", "context", "knowledge",
                        "paper", "note", "reflection", "transcript"]},
                    "memory_id": {"type": "string"},
                },
                "required": ["memory_type", "memory_id"],
            },
        },
        {
            "name": "echomind_health",
            "description": "Check EchoMind service health and version.",
            "inputSchema": {"type": "object", "properties": {}},
        },
    ]}


def handle_resources_list():
    return {"resources": [
        {"uri": "echomind://memory/stats", "name": "Memory Statistics",
         "description": "Memory storage statistics", "mimeType": "application/json"},
        {"uri": "echomind://config", "name": "Current Configuration",
         "description": "EchoMind runtime configuration", "mimeType": "application/json"},
    ]}


def handle_resource_read(uri):
    if uri in ("echomind://memory/stats", "echomind://config"):
        result = _api_get("/api/config")
        text = json.dumps(result, indent=2, default=str) if uri == "echomind://config" else json.dumps({"status": "ok", "note": "See /api/config for details"}, indent=2)
        return {"contents": [{"uri": uri, "mimeType": "application/json", "text": text}]}
    return {"contents": [{"uri": uri, "mimeType": "text/plain", "text": "Resource not found"}]}


def handle_tool_call(name, arguments):
    if name == "echomind_retrieve":
        result = _api_post("/api/memory/retrieve", {
            "user_id": arguments.get("user_id", "cli"),
            "query": arguments.get("query", ""),
            "max_results": arguments.get("max_results", 5),
            "project": arguments.get("project", "default"),
            "session_id": arguments.get("session_id", ""),
            "profile": arguments.get("profile", "default"),
        })
        if "error" in result:
            return {"content": [{"type": "text", "text": f"Error: {result['error']}"}]}
        memories = result.get("working_memory", [])
        if not memories:
            return {"content": [{"type": "text", "text": "No relevant memories found."}]}
        lines = [f"Found {len(memories)} relevant entr(ies):", ""]
        for i, m in enumerate(memories, 1):
            lines.append(f"[{i}] source={m.get('source','?')}  importance={m.get('importance',0):.2f}")
            lines.append(f"    {m.get('content','')[:400]}")
            lines.append("")
        return {"content": [{"type": "text", "text": "\n".join(lines)}]}

    elif name == "echomind_store":
        exp = arguments.get("experience_summary", "")
        ctx = arguments.get("context") or [{"role": "assistant", "content": exp}]
        result = _api_post("/api/memory/store", {
            "user_id": arguments.get("user_id", "cli"),
            "task_id": arguments.get("task_id", ""),
            "context": ctx,
            "task_status": arguments.get("task_status", "completed"),
            "success": arguments.get("success", True),
            "experience_summary": exp,
            "project": arguments.get("project", "default"),
            "session_id": arguments.get("session_id", ""),
            "profile": arguments.get("profile", "default"),
        })
        if "error" in result:
            return {"content": [{"type": "text", "text": f"Error storing: {result['error']}"}]}
        return {"content": [{"type": "text", "text": f"Memory stored."}]}

    elif name == "echomind_search":
        q = urllib.request.quote(arguments.get("query", ""))
        uid = arguments.get("user_id", "")
        limit = arguments.get("limit", 5)
        path = f"/api/memory/search-sessions?q={q}&limit={limit}"
        if uid:
            path += f"&user_id={urllib.request.quote(uid)}"
        result = _api_get(path)
        if "error" in result:
            return {"content": [{"type": "text", "text": f"Error: {result['error']}"}]}
        sessions = result.get("results", [])
        if not sessions:
            return {"content": [{"type": "text", "text": "No matching sessions."}]}
        lines = [f"Found {len(sessions)} session(s):", ""]
        for s in sessions[:limit]:
            lines.append(f"  {s.get('session_id','')}: {str(s.get('compressed_summary',''))[:150]}")
            lines.append("")
        return {"content": [{"type": "text", "text": "\n".join(lines)}]}

    elif name == "echomind_feedback":
        result = _api_post("/api/memory/feedback", {
            "user_id": arguments.get("user_id", ""),
            "task_id": arguments.get("task_id", ""),
            "feedback": arguments.get("feedback", ""),
            "retrieved_memories": arguments.get("memory_ids", []),
        })
        if "error" in result:
            return {"content": [{"type": "text", "text": f"Error: {result['error']}"}]}
        return {"content": [{"type": "text", "text": f"Feedback recorded."}]}

    elif name == "echomind_reflect":
        llm_response = arguments.get("llm_response")
        payload = {
            "user_id": arguments.get("user_id", ""),
            "count": arguments.get("count", 8),
            "platform": arguments.get("platform", "http"),
            "profile": arguments.get("profile", "default"),
        }
        if llm_response is not None:
            # Phase 2: process LLM response and write back to memory
            payload["llm_response"] = llm_response
            if arguments.get("record_ids"):
                payload["record_ids"] = arguments["record_ids"]
            result = _api_post("/api/reflect", payload)
            if "error" in result:
                return {"content": [{"type": "text", "text": f"Reflection error: {result['error']}"}]}
            return {"content": [{"type": "text", "text": (
                f"Reflection done. Insights: {result.get('insights', 0)}, "
                f"Preferences: {result.get('preferences', 0)}, "
                f"Knowledge: {result.get('knowledge', 0)}"
            )}]}
        else:
            # Phase 1: build prompt only (return for caller-side LLM processing)
            payload["llm_response"] = None
            result = _api_post("/api/reflect", payload)
            if "error" in result:
                return {"content": [{"type": "text", "text": f"Error: {result['error']}"}]}
            return {"content": [{"type": "text", "text": f"Reflection prepared for {result.get('record_count', 0)} records. "
                f"Prompt: {result.get('prompt', '')[:200]}... (use with llm_response to commit)"}]}

    elif name == "echomind_delete":
        mt = arguments.get("memory_type", "")
        mi = arguments.get("memory_id", "")
        result = _api_delete(f"/api/memory/{mt}/{mi}")
        if "error" in result:
            return {"content": [{"type": "text", "text": f"Error: {result['error']}"}]}
        return {"content": [{"type": "text", "text": f"Memory {mt}/{mi}: {result.get('status','unknown')}"}]}

    elif name == "echomind_health":
        result = _api_get("/health")
        if "error" in result:
            return {"content": [{"type": "text", "text": f"Not reachable: {result['error']}"}]}
        return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}

    return {"content": [{"type": "text", "text": f"Unknown tool: {name}"}]}


# ── Main MCP request dispatcher (used by both stdio and HTTP) ──

def handle_mcp_request(msg: dict) -> dict:
    """Dispatch a JSON-RPC 2.0 MCP request, return JSON-RPC response dict."""
    msg_id = msg.get("id")
    method = msg.get("method", "")
    params = msg.get("params", {})

    if method == "initialize":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}, "resources": {}},
            "serverInfo": {"name": "echomind-mcp", "version": "1.2.7"},
        }}
    elif method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": handle_tools_list()}
    elif method == "resources/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": handle_resources_list()}
    elif method == "resources/read":
        return {"jsonrpc": "2.0", "id": msg_id, "result": handle_resource_read(params.get("uri", ""))}
    elif method == "tools/call":
        return {"jsonrpc": "2.0", "id": msg_id, "result": handle_tool_call(params.get("name", ""), params.get("arguments", {}))}
    elif method.startswith("notifications/"):
        # M-7 fix: JSON-RPC notifications carry no `id` and expect NO response.
        # Returning a response frame confuses MCP clients (stdio gateway would
        # write a stray line to stdout). Signal "no response" with None and let
        # the transport layer skip writing it.
        return None
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": "Method not found"}}