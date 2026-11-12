# Client integrations — Hermes, Claude Code & OpenCode

> A blog version of this guide is available at
> [blog/echomind-client-integrations-article-en.md](../blog/echomind-client-integrations-article-en.md).

EchoMind exposes its memory in two layers:

1. **MCP tools** (always available): `echomind_retrieve`, `echomind_store`,
   `echomind_search`, `echomind_feedback`, `echomind_reflect`,
   `echomind_query`, `echomind_delete`, `echomind_health`.
2. **Automatic memory hooks** (this page): a thin client plugin recalls memory
   at session start and on each prompt, and stores completed turns — without
   the model deciding to call a tool.

Claude Code and OpenCode talk to the local EchoMind HTTP service (default
`http://127.0.0.1:8005`); Hermes integrates in-process through its native
MemoryProvider. No memory leaves the machine by default; see
[PRIVACY.md](PRIVACY.md).

```
Client plugin/hook ──HTTP──> /api/hooks/{claude|opencode} ──> retrieve_for_task / store
        │                                                        │
        └── MCP tools (explicit calls) ──────────────────────────┘
```

The hook endpoints are **fail-open**: if EchoMind is down or a payload is
malformed, the client continues without memory and the user's turn is never
blocked.

---

## Three client integrations

| Client | Integration | Auto recall | Auto store | Pre-compaction | Version |
|---|---|---|---|---|---|
| **Hermes Agent** | Native MemoryProvider | ✅ `prefetch` | ✅ `sync_turn` | ✅ `on_pre_compress` | v0.23.1 |
| **Claude Code** | Plugin + hooks | ✅ SessionStart / UserPromptSubmit | ✅ Stop / SessionEnd | ✅ PreCompact | 2.1.x |
| **OpenCode** | V1/V2 plugin | ✅ context hook | ✅ session.idle | ✅ compaction | 1.19.x |

## Hermes Agent (v0.23.1, native)

Hermes is EchoMind's deepest and longest-standing integration: instead of hook
scripts, it runs as a **MemoryProvider plugin** inside Hermes' agent loop.

### Lifecycle

| Lifecycle | EchoMind behavior |
|---|---|
| `initialize` | Opens/loads SQLite; resolves `hermes_home` / `agent_identity` (profile) / `default_user` / `project` |
| `prefetch` (before each turn) | Recalls and injects relevant memory |
| `sync_turn` (after each turn) | Stores the turn (`extract_knowledge=false` to avoid per-turn knowledge pollution) |
| `on_session_end` | Stores the session tail |
| `on_pre_compress` | Preserves memory before compaction |
| Tools | All 8 `echomind_*` MCP tools remain available |

### v0.23.1 adaptation (EchoMind v1.2.20)

- **MemoryProvider subclass** — works with the default in-process loader and `plugins.isolation: host` (the parent proxies it as a subclass).
- **Per-profile isolation (#140058)** — each provider instance owns its `ConfigManager` and `LLMClient`, so multiple profiles in one gateway cannot overwrite each other's endpoint/API key.
- **Context-aware background threads** — auto-reflection runs through `spawn_context_thread`, preserving the profile's `HERMES_HOME` and secret scope.
- **Optional hooks** — `recall_status()`, `identity_signature()` (gateway cache busting), `unavailable_reason()`.
- **Identity provenance** — `turn_author`, `user_id_alt`, `gateway_session_key`, `chat_*` are recorded in provenance (never rebind identity).
- **LLM auto-sync** — reads `model.default` / `model.base_url` / `model.provider` and `providers.<name>.*`, expands `${ENV}`, and only accepts OpenAI-compatible providers.
- **Auth** — HTTP/MCP support `ECHOMIND_API_KEY`; the secret written by `hermes memory setup` is read correctly.

### Install / activate

```bash
# 1. install the plugin (or use your plugin directory)
cp -r . ~/.hermes/plugins/echomind/

# 2. enable it as Hermes' memory provider
hermes config set memory.provider echomind

# 3. restart the local HTTP service if you use it
systemctl --user restart echomind.service
```

Hermes v0.20+ can also discover it via `register(ctx)`; `initialize` receives
`hermes_home`, `agent_identity`, `user_id` and related scope kwargs.

### Version status

- **v0.23.1** — adapted in EchoMind v1.2.20.
- Older Hermes — still works; the v0.23.x multiplex isolation and new hooks require EchoMind v1.2.20+.
- Hermes does not use `/api/hooks/*`; those endpoints serve Claude Code / OpenCode only.

## Claude Code (v2.1.x)

Plugin directory: [`integrations/claude-code/`](../integrations/claude-code/)

### Install

```bash
# 1. start EchoMind
python main.py            # or: systemctl --user start echomind.service
curl http://127.0.0.1:8005/health

# 2. load the plugin for a session (development)
claude --plugin-dir /path/to/echomind_memory.skill/integrations/claude-code
```

For a persistent install, add the directory to a Claude Code marketplace, or
copy it into your plugins location and enable it with `/plugin`. On Claude Code
2.1.275+ a marketplace install is:

```
/plugin install echomind-memory --marketplace <owner>/<repo>
```

### Hooks

| Event | Transport | Endpoint/behavior |
|---|---|---|
| `SessionStart` (`startup`/`resume`/`clear`/`compact`/`fork`) | **command** (`scripts/echomind_hook.py`) | `POST /api/hooks/claude` → memory briefing in `additionalContext` |
| `UserPromptSubmit` | **http** | recall the submitted prompt → `additionalContext` |
| `Stop` | **http** | store the completed turn (idempotent) |
| `PreCompact` (`manual`/`auto`) | **http** | store the transcript tail |
| `SessionEnd` | **http** | store the last turn (fallback) |

`SessionStart` uses a command hook because Claude Code only supports
`command`/`mcp_tool` on that event, and MCP tools are not connected at launch.
The script is stdlib-only and prints the hook JSON Claude reads.

### Configuration

| Env var | Default | Meaning |
|---|---|---|
| `ECHOMIND_URL` | `http://127.0.0.1:8005` | service base URL |
| `ECHOMIND_API_KEY` | — | sent as `X-API-Key` by MCP and hooks |
| `ECHOMIND_HOOK_PROJECT` | basename(`cwd`) | project scope |
| `ECHOMIND_HOOK_USER` | EchoMind `default_user` | user scope |
| `ECHOMIND_HOOK_PROFILE` | `default` | profile scope |

### Verify

```bash
claude plugin validate integrations/claude-code
claude mcp list          # echomind should connect
# inside a session:
/hooks                   # SessionStart / UserPromptSubmit / Stop registered
```

Windows: the SessionStart hook runs `python3`; edit `hooks/hooks.json` to
`python`/`py` if that is your interpreter.

---

## OpenCode (1.19.x)

Plugin directory: [`integrations/opencode/echomind-memory/`](../integrations/opencode/echomind-memory/)

The plugin is a **dual V1/V2** package: the default export has both a V1
`server()` function and a V2 `setup(ctx)`. It has no runtime dependency on either
plugin package.

### Install

```jsonc
// ~/.config/opencode/opencode.jsonc  (V2 / newest)
{
  "plugins": [
    { "package": "/absolute/path/to/integrations/opencode/echomind-memory" }
  ]
}
```

Older V1 loaders use the singular key (1.19.x normalizes it automatically):

```jsonc
{
  "plugin": ["/absolute/path/to/integrations/opencode/echomind-memory"]
}
```

Local plugin paths must be **directories**. OpenCode also discovers plugins
under `~/.config/opencode/plugins/` and `.opencode/plugins/`.

Keep the MCP tools as well:

```jsonc
{
  "mcp": {
    "echomind": {
      "type": "remote",
      "url": "http://127.0.0.1:8005/mcp",
      "enabled": true,
      "headers": { "X-API-Key": "{env:ECHOMIND_API_KEY}" }
    }
  }
}
```

### Behavior

| Capability | V1 (`@opencode-ai/plugin`) | V2 (`@opencode/plugin`) |
|---|---|---|
| Recall on prompt | `chat.message` | `session.hook("prompt")` |
| Inject context | `experimental.chat.system.transform` | `session.hook("context")` |
| Store on idle | `event` → `session.idle` | `ctx.event.subscribe({types:["session.idle"]})` |
| Compaction | `experimental.session.compacting` | `session.hook("compaction")` |

Recall is fetched once per prompt and injected into the next model request as a
`<echomind-memory>` block (not persisted into history). Stores are idempotent by
message id; the server also fingerprints the turn so compaction cannot duplicate
it.

### Configuration

`ECHOMIND_URL`, `ECHOMIND_API_KEY`, `ECHOMIND_HOOK_PROJECT`,
`ECHOMIND_HOOK_USER`, `ECHOMIND_HOOK_PROFILE` (same meanings as Claude Code).

### Version status

| OpenCode | Plugin API | Status |
|---|---|---|
| 1.19.x (V1 loader) | `@opencode-ai/plugin` | runtime-tested (1.19.5) |
| V2 (`@opencode/plugin` 2.x) | `Plugin.define` / `setup(ctx)` | implemented + `tsc --noEmit`; runtime needs a V2-capable build |

Type check the plugin:

```bash
cd integrations/opencode/echomind-memory
npm install && npm run typecheck
```

---

## Server hook endpoints

> These endpoints serve Claude Code / OpenCode only. Hermes uses the native MemoryProvider in-process and does not go through HTTP hooks.

### `POST /api/hooks/claude`

Accepts a Claude Code hook payload and returns the hook JSON Claude reads.

```json
// SessionStart / UserPromptSubmit response
{
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "<echomind-memory>…</echomind-memory>"
  }
}
```

Store-only events (`Stop`, `PreCompact`, `SessionEnd`) return `{}`.

### `POST /api/hooks/opencode`

| Action | Request | Response |
|---|---|---|
| `recall` | `{action, query, session_id, project, profile}` | `{"context": "...", "count": 3}` |
| `briefing` | `{action, session_id, project, profile}` | `{"context": "...", "count": 5}` |
| `store` | `{action, session_id, turn, messages, project, profile, extract_knowledge}` | `{"status": "stored\|duplicate\|empty\|error"}` |

Both endpoints require `X-API-Key` when `server.api_key` or
`ECHOMIND_API_KEY` is configured. Context is capped by
`hooks.max_context_chars` (default 8000).

---

## Troubleshooting

| Symptom | Check |
|---|---|
| No memory injected | Is `curl http://127.0.0.1:8005/health` OK? `claude --debug=hooks` / OpenCode logs |
| 403 on hooks/MCP | `ECHOMIND_API_KEY` set but not exported in the client's environment |
| Duplicate turns | Confirm the client sends stable `session_id`/message ids; the server dedups by turn fingerprint |
| SessionStart empty on Windows | `python3` not on PATH — change the hook command to `python` |
