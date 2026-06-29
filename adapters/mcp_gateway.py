#!/usr/bin/env python3
"""EchoMind MCP Server — wraps EchoMind HTTP API as Claude Code native tools.

Claude Code MCP protocol over stdio. Tools:
  - echomind_retrieve:  search memory by query
  - echomind_store:     store interaction into memory
  - echomind_search:    search session transcripts
  - echomind_feedback:  provide feedback on retrieval results
  - echomind_reflect:   trigger reflection on recent memories
  - echomind_delete:    delete a memory entry
  - echomind_health:    health check

Resources:
  - echomind://memory/stats : memory statistics
  - echomind://config       : current configuration

Register:
  claude mcp add echomind -- python3 ~/.local/bin/echomind-mcp
"""
import json
import sys
import urllib.request
import urllib.error
from urllib.parse import quote

ECHOMIND_URL = "http://127.0.0.1:8005"


def api_post(path, body):
    """Call EchoMind HTTP API and return parsed JSON response."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{ECHOMIND_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')}"}
    except Exception as e:
        return {"error": str(e)}


def api_get(path):
    """Call EchoMind HTTP API with GET."""
    try:
        req = urllib.request.Request(f"{ECHOMIND_URL}{path}", method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')}"}
    except Exception as e:
        return {"error": str(e)}


def api_delete(path):
    """Call EchoMind HTTP API with DELETE."""
    try:
        req = urllib.request.Request(f"{ECHOMIND_URL}{path}", method="DELETE")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}"}
    except Exception as e:
        return {"error": str(e)}


def handle_tools_list():
    return {
        "tools": [
            {
                "name": "echomind_retrieve",
                "description": "Search EchoMind long-term memory for relevant context. Call this before starting work to recall user preferences, past decisions, and related knowledge.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "user_id": {"type": "string", "description": "User identifier", "default": "cli"},
                        "max_results": {"type": "integer", "description": "Max entries", "default": 5},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "echomind_store",
                "description": "Store the current interaction result into EchoMind long-term memory. Call this after completing a significant task to persist what was done. Provide context as an array of messages, or use experience_summary for a quick single-message summary.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string", "default": "cli"},
                        "task_id": {"type": "string", "default": ""},
                        "task_status": {"type": "string", "default": "completed"},
                        "success": {"type": "boolean", "default": True},
                        "experience_summary": {"type": "string", "description": "Quick summary, used when context is not provided"},
                        "context": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "role": {"type": "string", "enum": ["user", "assistant", "system"]},
                                    "content": {"type": "string"}
                                }
                            },
                            "description": "Full conversation context (role/content pairs). Overrides experience_summary when provided."
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "echomind_search",
                "description": "Search session transcripts by keyword. Use to find past conversations and decisions.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "user_id": {"type": "string", "default": ""},
                        "limit": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "echomind_feedback",
                "description": "Provide feedback on a retrieval result to improve future memory rankings.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"},
                        "task_id": {"type": "string"},
                        "feedback": {"type": "string", "enum": ["positive", "negative"]},
                        "memory_ids": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": "Retrieved memory entries",
                        },
                    },
                    "required": ["user_id", "task_id", "feedback"],
                },
            },
            {
                "name": "echomind_reflect",
                "description": "Trigger reflection on recent memories. Extracts insights, preferences, and rules from recent episodic records.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"},
                        "count": {"type": "integer", "default": 8},
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
                        "memory_type": {
                            "type": "string",
                            "enum": ["user", "task", "experience", "context", "knowledge", "paper", "note", "reflection", "transcript"],
                        },
                        "memory_id": {"type": "string"},
                    },
                    "required": ["memory_type", "memory_id"],
                },
            },
            {
                "name": "echomind_health",
                "description": "Check EchoMind service health and version.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
        ]
    }


def handle_resources_list():
    return {
        "resources": [
            {
                "uri": "echomind://memory/stats",
                "name": "Memory Statistics",
                "description": "Memory storage statistics",
                "mimeType": "application/json",
            },
            {
                "uri": "echomind://config",
                "name": "Current Configuration",
                "description": "EchoMind runtime configuration",
                "mimeType": "application/json",
            },
        ]
    }


def handle_resource_read(uri):
    if uri == "echomind://memory/stats":
        result = api_get("/api/config")
        if "error" in result:
            return {"contents": [{"uri": uri, "mimeType": "application/json", "text": json.dumps({"error": result["error"]})}]}
        return {"contents": [{"uri": uri, "mimeType": "application/json", "text": json.dumps({"status": "ok", "note": "See /api/config for details"}, indent=2)}]}
    elif uri == "echomind://config":
        result = api_get("/api/config")
        if "error" in result:
            return {"contents": [{"uri": uri, "mimeType": "application/json", "text": json.dumps({"error": result["error"]})}]}
        return {"contents": [{"uri": uri, "mimeType": "application/json", "text": json.dumps(result, indent=2, default=str)}]}
    return {"contents": [{"uri": uri, "mimeType": "text/plain", "text": "Resource not found"}]}


def handle_tool_call(name, arguments):
    # ── Retrieve ──
    if name == "echomind_retrieve":
        query = arguments.get("query", "")
        user_id = arguments.get("user_id", "cli")
        max_results = arguments.get("max_results", 5)
        result = api_post("/api/memory/retrieve", {
            "user_id": user_id, "query": query, "max_results": max_results,
        })
        if "error" in result:
            return {"content": [{"type": "text", "text": f"Error: {result['error']}"}]}
        memories = result.get("working_memory", [])
        if not memories:
            return {"content": [{"type": "text", "text": "No relevant memories found."}]}
        lines = [f"Found {len(memories)} relevant memory entr(ies):", ""]
        for i, m in enumerate(memories, 1):
            lines.append(f"[{i}] source={m.get('source','unknown')}  importance={m.get('importance',0):.2f}")
            lines.append(f"    {m.get('content','')[:400]}")
            lines.append("")
        return {"content": [{"type": "text", "text": "\n".join(lines)}]}

    # ── Store ──
    elif name == "echomind_store":
        user_id = arguments.get("user_id", "cli")
        task_id = arguments.get("task_id", "")
        task_status = arguments.get("task_status", "completed")
        success = arguments.get("success", True)
        experience_summary = arguments.get("experience_summary", "")
        context = arguments.get("context", None)
        if not context:
            context = [{"role": "assistant", "content": experience_summary}]
        result = api_post("/api/memory/store", {
            "user_id": user_id,
            "task_id": task_id or f"task:{task_status}",
            "context": context,
            "task_status": task_status,
            "success": success,
            "experience_summary": experience_summary,
        })
        if "error" in result:
            return {"content": [{"type": "text", "text": f"Error storing memory: {result['error']}"}]}
        return {"content": [{"type": "text", "text": f"Memory stored. summary: {experience_summary[:200]}"}]}

    # ── Search ──
    elif name == "echomind_search":
        query = arguments.get("query", "")
        user_id = arguments.get("user_id", "")
        limit = arguments.get("limit", 5)
        path = f"/api/memory/search-sessions?q={quote(query)}&limit={limit}"
        if user_id:
            path += f"&user_id={quote(user_id)}"
        result = api_get(path)
        if "error" in result:
            return {"content": [{"type": "text", "text": f"Error: {result['error']}"}]}
        sessions = result.get("results", [])
        if not sessions:
            return {"content": [{"type": "text", "text": "No matching sessions found."}]}
        lines = [f"Found {len(sessions)} session(s):", ""]
        for s in sessions[:limit]:
            lines.append(f"  Session: {s.get('session_id','')}")
            lines.append(f"  Summary: {str(s.get('compressed_summary',''))[:200]}")
            lines.append("")
        return {"content": [{"type": "text", "text": "\n".join(lines)}]}

    # ── Feedback ──
    elif name == "echomind_feedback":
        user_id = arguments.get("user_id", "")
        task_id = arguments.get("task_id", "")
        feedback = arguments.get("feedback", "")
        memory_ids = arguments.get("memory_ids", [])
        result = api_post("/api/memory/feedback", {
            "user_id": user_id,
            "task_id": task_id,
            "feedback": feedback,
            "retrieved_memories": memory_ids,
        })
        if "error" in result:
            return {"content": [{"type": "text", "text": f"Error: {result['error']}"}]}
        return {"content": [{"type": "text", "text": f"Feedback '{feedback}' recorded for task {task_id}."}]}

    # ── Reflect ──
    elif name == "echomind_reflect":
        user_id = arguments.get("user_id", "")
        count = arguments.get("count", 8)
        result = api_post("/api/reflect", {
            "user_id": user_id, "count": count, "llm_response": None,
        })
        if "error" in result:
            return {"content": [{"type": "text", "text": f"Error: {result['error']}"}]}
        prompt = result.get("prompt", "")
        record_count = result.get("record_count", 0)
        if not prompt:
            return {"content": [{"type": "text", "text": f"Reflection prompt built for {record_count} records but engine returned empty."}]}
        return {"content": [{"type": "text", "text": f"Reflection prepared for {record_count} records. Prompt length: {len(prompt)} chars.\n\nPrompt preview:\n{prompt[:500]}"}]}

    # ── Delete ──
    elif name == "echomind_delete":
        memory_type = arguments.get("memory_type", "")
        memory_id = arguments.get("memory_id", "")
        result = api_delete(f"/api/memory/{memory_type}/{memory_id}")
        if "error" in result:
            return {"content": [{"type": "text", "text": f"Error: {result['error']}"}]}
        status = result.get("status", "unknown")
        return {"content": [{"type": "text", "text": f"Memory {memory_type}/{memory_id}: {status}"}]}

    # ── Health ──
    elif name == "echomind_health":
        result = api_get("/health")
        if "error" in result:
            return {"content": [{"type": "text", "text": f"EchoMind service not reachable: {result['error']}"}]}
        return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}

    else:
        return {"content": [{"type": "text", "text": f"Unknown tool: {name}"}]}


def main():
    """MCP stdio server loop — reads JSON-RPC from stdin, writes to stdout."""
    sys.stderr.write("[echomind-mcp] started, waiting for requests...\n")
    sys.stderr.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        msg_id = msg.get("id")
        method = msg.get("method")
        params = msg.get("params", {})

        if method == "initialize":
            response = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}, "resources": {}},
                    "serverInfo": {"name": "echomind-mcp", "version": "1.2.0"},
                },
            }

        elif method == "tools/list":
            response = {"jsonrpc": "2.0", "id": msg_id, "result": handle_tools_list()}

        elif method == "resources/list":
            response = {"jsonrpc": "2.0", "id": msg_id, "result": handle_resources_list()}

        elif method == "resources/read":
            uri = params.get("uri", "")
            response = {"jsonrpc": "2.0", "id": msg_id, "result": handle_resource_read(uri)}

        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {})
            result = handle_tool_call(tool_name, tool_args)
            response = {"jsonrpc": "2.0", "id": msg_id, "result": result}

        elif method in ("notifications/initialized",):
            continue

        else:
            response = {"jsonrpc": "2.0", "id": msg_id, "result": {}}

        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()