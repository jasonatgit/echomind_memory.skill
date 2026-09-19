## API Endpoints (HTTP Mode)

| Method | Endpoint | Description |
|------|------|------|
| `POST` | `/api/memory/retrieve` | Retrieve task memory (supports project, session_id, profile filtering) |
| `POST` | `/api/memory/store` | Store conversation context (supports project, session_id, correction, profile) |
| `POST` | `/api/memory/feedback` | Record feedback for RL optimization |
| `POST` | `/api/memory/sync-code` | Sync project code style memory |
| `GET` | `/api/memory/search-sessions` | Search session transcripts |
| `GET` | `/api/memory/health` | Memory health report (briefing + states + flags) |
| `POST` | `/api/memory/{type}/{id}/state` | Set memory lifecycle state |
| `POST` | `/api/memory/cleanup` | TTL-based memory cleanup |
| `DELETE` | `/api/memory/{type}/{id}` | Delete single memory record |
| `POST` | `/api/memory/delete-user` | Delete all user memories |
| `POST` | `/api/memory/query` | Structured provenance query (project/tags/origin/date predicates, no scoring) |
| `POST` | `/api/research/paper` | Add research paper |
| `POST` | `/api/research/note` | Add research note |
| `GET` | `/api/knowledge/{id}/evolution` | Query knowledge evolution chain |
| `GET` | `/api/config` | Read current configuration |
| `POST` | `/api/config/parameter` | Set runtime config parameter (section whitelist; `api_key` is protected) |
| `POST` | `/api/config/reload` | Reload configuration from disk |
| `POST` | `/api/reflect` | Self-reflection (two-phase: build prompt or process result, supports profile) |
| `POST` | `/mcp` | MCP JSON-RPC endpoint (Streamable HTTP; notifications return an empty 202) |
| `GET` | `/health` | Health check |

> **Error semantics (v1.2.13+):** `DELETE /api/memory/{type}/{id}` returns **400** for an unknown memory type (previously 500). `/api/reflect` returns **429** when the per-user daily reflection limit is reached and **400** for a parse failure / low-confidence result — failed reflections refund their quota slot and never consume the daily limit.

### Key Request Parameters

#### POST /api/memory/retrieve
| Parameter | Type | Required | Default | Description |
|-----------|------|:---:|---------|-------------|
| `user_id` | string | ✅ | | User identifier |
| `query` | string | ✅ | | Search/retrieval query |
| `task_id` | string | | | Ongoing task ID |
| `platform` | string | | | Platform tag (hermes, http, etc.) |
| `max_results` | integer | | 5 | Max memories to return |
| `project` | string | | "default" | Project identifier for isolation |
| `session_id` | string | | "" | Session identifier for context grouping |
| `profile` | string | | "default" | User profile for memory isolation |
| `tags` | array | | [] | Tag filter (case-insensitive; OR by default) |
| `tags_match_all` | boolean | | false | True requires every tag to match (AND) |
| `origin_platform` | string | | | Transport filter (mcp/http/hermes/cli) |
| `origin_client` | string | | | Producing client filter (claude-code/opencode/...) |

#### POST /api/memory/store
| Parameter | Type | Required | Default | Description |
|-----------|------|:---:|---------|-------------|
| `user_id` | string | ✅ | | User identifier |
| `task_id` | string | ✅ | | Task identifier |
| `context` | array | ✅ | | Conversation messages (role/content pairs) |
| `task_status` | string | ✅ | | completed / failed / pending |
| `success` | boolean | | false | Whether task succeeded |
| `experience_summary` | string | | | Quick summary |
| `platform` | string | | | Platform tag |
| `title` | string | | | Task title |
| `project` | string | | "default" | Project identifier |
| `session_id` | string | | "" | Session identifier |
| `correction` | boolean | | false | True if user is correcting agent |
| `profile` | string | | "default" | User profile |
| `tags` | array | | [] | Caller tags (priority); auto topic tags fill the rest |
| `origin_client` | string | | | Producing client (claude-code/opencode/...); stored with the record's provenance |

#### POST /api/memory/query
Structured provenance query (v1.2.14) — exact source predicates, **no relevance scoring**. Results merge across the selected memory tables, newest first. One day's memories: `date_from` = `date_to` = `YYYY-MM-DD`.

| Parameter | Type | Required | Default | Description |
|-----------|------|:---:|---------|-------------|
| `user_id` | string | ✅ | | User identifier |
| `profile` | string | | "default" | User profile |
| `memory_type` | string | | "all" | knowledge/experience/task/context/research/transcript/reflection, comma-separated, or "all" |
| `project` | string | | | Project scope |
| `tags` | array | | [] | Tag filter (case-insensitive) |
| `tags_match_all` | boolean | | false | True requires every tag (AND) |
| `origin_platform` | string | | | Transport filter (mcp/http/hermes/cli) |
| `origin_client` | string | | | Producing client filter |
| `date_from` / `date_to` | string | | | Inclusive date bounds (YYYY-MM-DD) |
| `limit` | integer | | 20 | Max records |

Unknown `memory_type` values return **400**. Each result carries `memory_type`, `id`, `content`, `tags`, `project`, `origin_platform`, `origin_client`, `created_at`, and the full provenance `envelope`.

#### POST /api/reflect
| Parameter | Type | Required | Default | Description |
|-----------|------|:---:|---------|-------------|
| `user_id` | string | ✅ | | User identifier |
| `count` | integer | | 8 | Number of recent records to reflect on |
| `platform` | string | | "http" | Platform tag |
| `record_ids` | array | | | Specific record IDs to reflect on |
| `llm_response` | string | | | LLM response for Phase 2 (omit for Phase 1 prompt) |
| `profile` | string | | "default" | User profile |

### MCP Tools

The MCP protocol exposes the following tools (via `POST /mcp` or `mcp_gateway.py` stdio):

| Tool | Description |
|------|-------------|
| `echomind_retrieve` | Search long-term memory by query (supports project/session_id/profile, tags, origin) |
| `echomind_store` | Store interaction into memory (supports project/session_id/profile, caller tags, origin_client) |
| `echomind_search` | Search session transcripts by keyword |
| `echomind_feedback` | Provide positive/negative feedback on retrieval |
| `echomind_reflect` | Trigger reflection (Phase 1: build prompt; Phase 2 with llm_response: commit) |
| `echomind_query` | Structured provenance query by exact predicates: project, tags (OR/AND), origin_client/origin_platform, date range, memory type — no relevance scoring |
| `echomind_delete` | Delete a memory entry |
| `echomind_health` | Health check |