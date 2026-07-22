## API Endpoints (HTTP Mode)

| Method | Endpoint | Description |
|------|------|------|
| `POST` | `/api/memory/retrieve` | Retrieve task memory |
| `POST` | `/api/memory/store` | Store conversation context |
| `POST` | `/api/memory/feedback` | Record feedback for RL optimization |
| `POST` | `/api/memory/sync-code` | Sync project code style memory |
| `GET` | `/api/memory/search-sessions` | Search session transcripts |
| `GET` | `/api/memory/health` | Memory health report (briefing + states + flags) |
| `POST` | `/api/memory/{type}/{id}/state` | Set memory lifecycle state |
| `POST` | `/api/memory/cleanup` | TTL-based memory cleanup |
| `DELETE` | `/api/memory/{type}/{id}` | Delete single memory record |
| `POST` | `/api/memory/delete-user` | Delete all user memories |
| `POST` | `/api/research/paper` | Add research paper |
| `POST` | `/api/research/note` | Add research note |
| `GET` | `/api/knowledge/{id}/evolution` | Query knowledge evolution chain |
| `GET` | `/api/config` | Read current configuration |
| `POST` | `/api/config/parameter` | Set runtime config parameter |
| `POST` | `/api/config/reload` | Reload configuration from disk |
| `POST` | `/api/reflect` | Self-reflection |
| `POST` | `/mcp` | MCP JSON-RPC endpoint (Streamable HTTP) |
| `GET` | `/health` | Health check |

---
