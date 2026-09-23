"""Shared MCP tool handlers used by both stdio gateway and HTTP MCP endpoint.

Purpose: eliminate code duplication between mcp_gateway.py (stdio) and
http_api.py (Streamable HTTP MCP). Both import handle_tools_list,
handle_tool_call, handle_resources_list, handle_resource_read, and
handle_mcp_request from this module.
"""

import json
import logging
import os
import urllib.request
import urllib.error

from core._reflective_version import ECHOMIND_VERSION

logger = logging.getLogger("McpCommon")

ECHOMIND_URL = "http://127.0.0.1:8005"

# v1.2.14 provenance: the connecting MCP client's identity, captured from the
# initialize handshake's clientInfo.name (normalized by provenance). Empty
# until an initialize arrives; tool calls then default origin_client to it.
_MCP_CLIENT = ""
# F6 (v1.2.15 audit): the HTTP /mcp endpoint serves many clients from ONE
# process, so a single module-global let client B's calls be attributed to
# whichever client initialized last. HTTP connections are keyed by session;
# the stdio gateway stays on the module global (one process per connection).
_MCP_CLIENT_BY_SESSION: dict = {}


def _default_origin_client(arguments: dict, session_id: str = "",
                           header_client: str = "") -> str:
    """origin_client for an MCP tool call.

    Precedence: explicit argument > per-request header identity > per-session
    identity (HTTP) > stdio handshake identity > transport value "mcp".
    """
    explicit = str(arguments.get("origin_client", "") or "").strip()
    if explicit:
        return explicit
    if header_client:
        return header_client
    if session_id and _MCP_CLIENT_BY_SESSION.get(session_id):
        return _MCP_CLIENT_BY_SESSION[session_id]
    if _MCP_CLIENT:
        return _MCP_CLIENT
    return "mcp"


def _default_user_id(arguments: dict) -> str:
    """Identity for an MCP tool call (v1.2.14 usage-path fix).

    Precedence: explicit argument > config `default_user` > "cli". The MCP
    schema marks user_id optional with a default, so clients (Claude Code,
    opencode) frequently omit it; the old hard-coded "cli" fallback then mixed
    every client's memories under one shared identity. Scoping the fallback to
    the configured default user keeps identities unified while the *origin*
    (origin_client/origin_platform) still distinguishes the source client.
    """
    uid = str(arguments.get("user_id") or "").strip()
    if uid:
        return uid
    try:
        from core.config_manager import get_config_manager
        return get_config_manager().get_top_level("default_user", "cli") or "cli"
    except Exception:
        return "cli"


def _resolve_project(explicit: str) -> str:
    """Resolve a non-default project scope for MCP traffic.

    Precedence: explicit argument > config `default_project` (top-level key in
    echomind_config.yaml, the same value the HTTP server uses) > "default".
    DSH/Zcode streamable-http transports do not inject a working directory, so
    an operator can pin a host-wide default project via the config; otherwise
    the memory lands in the shared "default" namespace and cross-agent leakage
    returns. "default" is only used when nothing else is configured.
    """
    if explicit and explicit != "default":
        return explicit
    try:
        from core.config_manager import get_config_manager
        cfg = get_config_manager().get_top_level("default_project", "default")
        if cfg and cfg != "default":
            return cfg
    except Exception:
        pass
    return explicit or "default"


def _safe_int(value, default: int = 0) -> int:
    """Coerce an MCP argument to int without raising.

    P2-15 (v1.2.16 audit): client arguments arrive as JSON values; a float
    like ``3.9`` truncates to 3, a numeric string ``"4"`` parses, and anything
    else (``"abc"``, ``None``) falls back to ``default`` instead of bubbling a
    ValueError out of the tool handler with a stack-trace leak.
    """
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _resolve_api_key() -> str:
    """Resolve the API key using the SAME precedence as the HTTP server.

    C-H2/P4: previously the gateway read only the ECHOMIND_API_KEY env var at
    import time, while the server (http_api.verify_api_key) reads live from the
    config manager's server.api_key. A user who configured server.api_key in
    echomind_config.yaml but never exported the env var got 403s on every MCP
    tool. Now the config source wins (matching the server), with env as the
    fallback for the stdio-gateway-in-a-different-process case.

    It is resolved lazily per request (not cached at import) so hot config
    reloads behave the same way the server's verify_api_key does.
    """
    try:
        from core.config_manager import get_config_manager
        cfg_key = get_config_manager().get_section("server").get("api_key", "")
        if cfg_key:
            return cfg_key
    except Exception:
        # ConfigManager may not be importable/usable in a bare stdio context;
        # fall through to env.
        pass
    return os.environ.get("ECHOMIND_API_KEY", "") or os.environ.get("ECHOMIND_API_TOKEN", "")


def _headers(extra=None) -> dict:
    h = {"Content-Type": "application/json"}
    key = _resolve_api_key()
    if key:
        h["X-API-Key"] = key
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
        # P2-9 (v1.2.17 review): don't paste the raw response body back to the
        # MCP client — it can carry internal paths/SQL that the HTTP-layer
        # sanitisation (P2-10) just removed. Surface status + the parsed
        # `detail` field only, and log the body server-side.
        status = getattr(e, "code", "?")
        detail = ""
        try:
            _body = json.loads(e.read().decode("utf-8", errors="replace"))
            if isinstance(_body, dict):
                detail = str(_body.get("detail") or _body.get("status") or "")
        except Exception:
            detail = ""
        logger.error("_api_post HTTP %s: %s", status, detail or "(no detail)")
        return {"error": f"HTTP {status}" + (f": {detail}" if detail else "")}
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
                    "platform": {"type": "string", "default": "mcp"},
                    "max_results": {"type": "integer", "default": 5},
                    "project": {"type": "string", "default": "default"},
                    "session_id": {"type": "string", "default": ""},
                    "profile": {"type": "string", "default": "default"},
                    "tags": {"type": "array", "items": {"type": "string"},
                             "description": "Optional. Tag filter (case-insensitive)."},
                    "tags_match_all": {"type": "boolean", "default": False,
                                       "description": "True requires every tag (AND); default OR."},
                    "origin_client": {"type": "string",
                                      "description": "Optional. Source client filter (defaults to the connecting client)."},
                    "origin_platform": {"type": "string",
                                        "description": "Optional. Transport filter (mcp/http/hermes/cli)."},
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
                    "platform": {"type": "string", "default": "mcp"},
                    "project": {"type": "string", "default": "default"},
                    "session_id": {"type": "string", "default": ""},
                    "profile": {"type": "string", "default": "default"},
                    "correction": {"type": "boolean", "default": False,
                                   "description": "True if this store is a fix/correction of a prior turn"},
                    "turn": {"type": "integer", "default": 0,
                             "description": "Optional. Turn index in the source session; recorded on evolution rows."},
                    "tags": {"type": "array", "items": {"type": "string"},
                             "description": "Optional. Caller tags (priority); auto topic tags fill the rest."},
                    "origin_client": {"type": "string",
                                      "description": "Optional. Producing client (defaults to the connecting client)."},
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
                    "profile": {"type": "string", "default": "default"},
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
            "name": "echomind_query",
            "description": "Structured provenance query over memory records by exact source predicates (project, tags, origin client/platform, date range, memory type) — no relevance scoring. Use echomind_retrieve for semantic search.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "default": "cli"},
                    "profile": {"type": "string", "default": "default"},
                    "memory_type": {"type": "string", "default": "all",
                                    "description": "knowledge/experience/task/context/research/transcript/reflection, comma-separated, or 'all'."},
                    "project": {"type": "string", "description": "Optional. Project scope."},
                    "tags": {"type": "array", "items": {"type": "string"},
                             "description": "Optional. Tag filter (case-insensitive)."},
                    "tags_match_all": {"type": "boolean", "default": False,
                                       "description": "True requires every tag (AND); default OR."},
                    "origin_client": {"type": "string",
                                      "description": "Optional. Producing client (claude-code/opencode/...)."},
                    "origin_platform": {"type": "string",
                                        "description": "Optional. Transport (mcp/http/hermes/cli)."},
                    "date_from": {"type": "string",
                                  "description": "Optional. YYYY-MM-DD (inclusive)."},
                    "date_to": {"type": "string",
                                "description": "Optional. YYYY-MM-DD (inclusive)."},
                    "limit": {"type": "integer", "default": 20},
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
    if uri == "echomind://memory/stats":
        # L-R7: return real memory statistics from the health endpoint instead
        # of the previous static "see /api/config" placeholder text.
        result = _api_get("/api/memory/health")
        return {"contents": [{"uri": uri, "mimeType": "application/json",
                              "text": json.dumps(result, indent=2, default=str)}]}
    if uri == "echomind://config":
        result = _api_get("/api/config")
        return {"contents": [{"uri": uri, "mimeType": "application/json",
                              "text": json.dumps(result, indent=2, default=str)}]}
    return {"contents": [{"uri": uri, "mimeType": "text/plain", "text": "Resource not found"}]}


def handle_tool_call(name, arguments, session_id: str = "",
                     header_client: str = ""):
    """Dispatch an MCP tools/call. session_id/header_client scope the origin
    attribution per HTTP connection (F6, v1.2.15); the stdio gateway omits
    both and falls back to the handshake global."""
    if name == "echomind_retrieve":
        # M-R7 fix: tag MCP-sourced traffic with an explicit platform instead
        # of letting it fall through to None → "default", which made MCP data
        # indistinguishable from and isolated from Hermes/HTTP data.
        result = _api_post("/api/memory/retrieve", {
            "user_id": _default_user_id(arguments),
            "query": arguments.get("query", ""),
            "platform": arguments.get("platform", "mcp"),
            "max_results": arguments.get("max_results", 5),
            "project": _resolve_project(arguments.get("project", "default")),
            "session_id": arguments.get("session_id", ""),
            "profile": arguments.get("profile", "default"),
            # v1.2.14: tag filter plumbed through (case-insensitive).
            "tags": arguments.get("tags", []),
            "tags_match_all": bool(arguments.get("tags_match_all", False)),
            # P0-1 fix (v1.2.14 review): origin filters apply ONLY on explicit
            # arguments. The captured clientInfo marks STORES (provenance); it
            # must not hard-filter retrievals — combined with the endpoint's
            # former "http" strong-cast it made every MCP retrieval return
            # nothing. Empty → None keeps the core transparent by default.
            "origin_client": arguments.get("origin_client") or None,
            "origin_platform": arguments.get("origin_platform") or None,
        })
        if "error" in result:
            return {"content": [{"type": "text", "text": f"Error: {result['error']}"}]}
        memories = result.get("working_memory", [])
        if not memories:
            return {"content": [{"type": "text", "text": "No relevant memories found."}]}
        # v1.2.14 provenance: surface each entry's source so the calling agent
        # can see where a memory came from at a glance.
        from core.provenance import envelope_from_record, format_origin_line
        lines = [f"Found {len(memories)} relevant entr(ies):", ""]
        for i, m in enumerate(memories, 1):
            lines.append(f"[{i}] source={m.get('source','?')}  importance={m.get('importance',0):.2f}")
            env = envelope_from_record(m.get("metadata"))
            origin = format_origin_line(env)
            if origin:
                lines.append(f"    origin={origin}")
            lines.append(f"    {m.get('content','')[:400]}")
            lines.append("")
        return {"content": [{"type": "text", "text": "\n".join(lines)}]}

    elif name == "echomind_store":
        exp = arguments.get("experience_summary", "")
        ctx = arguments.get("context") or [{"role": "assistant", "content": exp}]
        result = _api_post("/api/memory/store", {
            "user_id": _default_user_id(arguments),
            "task_id": arguments.get("task_id", ""),
            "context": ctx,
            "task_status": arguments.get("task_status", "completed"),
            "success": arguments.get("success", True),
            "experience_summary": exp,
            "platform": arguments.get("platform", "mcp"),
            "project": _resolve_project(arguments.get("project", "default")),
            "session_id": arguments.get("session_id", ""),
            "profile": arguments.get("profile", "default"),
            "correction": arguments.get("correction", False),
            # v1.2.14: caller tags take priority over auto topic tags.
            "tags": arguments.get("tags", []),
            # v1.2.14: origin provenance (explicit arg > captured clientInfo).
            "origin_client": _default_origin_client(arguments, session_id, header_client),
            # F3b (v1.2.15 audit): turn index recorded on evolution rows.
            # P2-15 (v1.2.16 audit): guard the coercion — a non-numeric `turn`
            # string from a client used to raise ValueError and leak
            # "-32603 ... path/to/store" back to the caller; safe-coerce to 0.
            "turn": _safe_int(arguments.get("turn", 0), default=0),
        })
        if "error" in result:
            return {"content": [{"type": "text", "text": f"Error storing: {result['error']}"}]}
        return {"content": [{"type": "text", "text": f"Memory stored."}]}

    elif name == "echomind_search":
        q = urllib.request.quote(arguments.get("query", ""))
        uid = _default_user_id(arguments)
        # P2-8 (v1.2.17 review): limit is interpolated into the query string —
        # an uncoerced value could inject extra params ("5&user_id=other").
        # Coerce to a bounded int like `turn` (P2-15) instead of trusting it.
        limit = _safe_int(arguments.get("limit", 5), default=5)
        limit = max(1, min(limit, 100))
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
            "user_id": _default_user_id(arguments),
            "task_id": arguments.get("task_id", ""),
            "feedback": arguments.get("feedback", ""),
            "retrieved_memories": arguments.get("memory_ids", []),
            "profile": arguments.get("profile", "default"),
        })
        if "error" in result:
            return {"content": [{"type": "text", "text": f"Error: {result['error']}"}]}
        return {"content": [{"type": "text", "text": f"Feedback recorded."}]}

    elif name == "echomind_reflect":
        llm_response = arguments.get("llm_response")
        payload = {
            "user_id": _default_user_id(arguments),
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

    elif name == "echomind_query":
        payload = {
            "user_id": _default_user_id(arguments),
            "profile": arguments.get("profile", "default"),
            "memory_type": arguments.get("memory_type", "all"),
            "project": arguments.get("project") or None,
            "tags": arguments.get("tags", []),
            "tags_match_all": bool(arguments.get("tags_match_all", False)),
            "origin_platform": arguments.get("origin_platform") or None,
            "origin_client": arguments.get("origin_client") or None,
            "date_from": arguments.get("date_from") or None,
            "date_to": arguments.get("date_to") or None,
            "limit": arguments.get("limit", 20),
        }
        result = _api_post("/api/memory/query", payload)
        if "error" in result:
            return {"content": [{"type": "text", "text": f"Error: {result['error']}"}]}
        records = result.get("results", [])
        if not records:
            return {"content": [{"type": "text", "text": "No memories match these predicates."}]}
        from core.provenance import format_origin_line
        lines = [f"Found {len(records)} record(s):", ""]
        for i, r in enumerate(records, 1):
            origin = format_origin_line(r.get("envelope"), r.get("created_at", ""))
            lines.append(f"[{i}] type={r.get('memory_type')}  {origin}")
            lines.append(f"    {str(r.get('content',''))[:200]}")
            lines.append("")
        return {"content": [{"type": "text", "text": "\n".join(lines)}]}

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

def handle_mcp_request(msg: dict, session_id: str = "",
                       header_client: str = "") -> dict:
    """Dispatch a JSON-RPC 2.0 MCP request, return JSON-RPC response dict.

    session_id/header_client come from the HTTP transport (Mcp-Session-Id /
    X-Client-Name headers) and scope the captured client identity per
    connection; the stdio gateway omits both.
    """
    msg_id = msg.get("id")
    method = msg.get("method", "")
    params = msg.get("params", {})

    if method == "initialize":
        # v1.2.14 provenance: capture the connecting client's identity from
        # clientInfo.name so later stores/retrieves default origin_client to
        # the real source (claude-code / opencode / ...) instead of a generic
        # "mcp". The stdio gateway is a single process, so a module-level
        # value is per-connection; over HTTP the identity is keyed by the
        # transport session (F6, v1.2.15) so concurrent clients cannot
        # overwrite each other's attribution. An initialize-less call falls
        # back to the explicit argument, header identity, or "mcp".
        client_info = params.get("clientInfo")
        if isinstance(client_info, dict) and client_info.get("name"):
            from core.provenance import normalize_origin_client
            name = normalize_origin_client(client_info["name"])
            if name:
                if session_id:
                    _MCP_CLIENT_BY_SESSION[session_id] = name
                    # bound the map so long-lived servers don't grow unbounded
                    if len(_MCP_CLIENT_BY_SESSION) > 1024:
                        _MCP_CLIENT_BY_SESSION.pop(next(iter(_MCP_CLIENT_BY_SESSION)))
                else:
                    global _MCP_CLIENT
                    _MCP_CLIENT = name
        return {"jsonrpc": "2.0", "id": msg_id, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}, "resources": {}},
            "serverInfo": {"name": "echomind-mcp", "version": ECHOMIND_VERSION},
        }}
    elif method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": handle_tools_list()}
    elif method == "resources/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": handle_resources_list()}
    elif method == "resources/read":
        return {"jsonrpc": "2.0", "id": msg_id, "result": handle_resource_read(params.get("uri", ""))}
    elif method == "tools/call":
        return {"jsonrpc": "2.0", "id": msg_id, "result": handle_tool_call(
            params.get("name", ""), params.get("arguments", {}),
            session_id=session_id, header_client=header_client)}
    elif method.startswith("notifications/"):
        # M-7 fix: JSON-RPC notifications carry no `id` and expect NO response.
        # Returning a response frame confuses MCP clients (stdio gateway would
        # write a stray line to stdout). Signal "no response" with None and let
        # the transport layer skip writing it.
        return None
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": "Method not found"}}