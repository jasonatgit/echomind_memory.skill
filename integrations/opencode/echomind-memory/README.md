# EchoMind Memory — OpenCode plugin (dual V1/V2)

Automatic long-term memory for OpenCode. It delegates all memory work to the
local EchoMind HTTP service and speaks **both** plugin APIs from one entrypoint:

- **V1** (`OpenCode <= 1.19.x`, `@opencode-ai/plugin`): `chat.message` →
  `experimental.chat.system.transform` injects recall; the `event` hook stores on
  `session.idle`; `experimental.session.compacting` preserves memory.
- **V2** (documented `@opencode/plugin` API): `session.hook("prompt"/"context"/
  "compaction")` + `event.subscribe("session.idle")`.

Requires the EchoMind HTTP service (default `http://127.0.0.1:8005`).

## Install

```bash
# 1. Start EchoMind
python main.py            # or: systemctl --user start echomind.service
curl http://127.0.0.1:8005/health
```

2. Point OpenCode at this plugin directory (V2 configuration shown):

```jsonc
// ~/.config/opencode/opencode.jsonc  (V2 / newest)
{
  "plugins": [
    { "package": "/absolute/path/to/integrations/opencode/echomind-memory" }
  ]
}
```

For the V1 plugin key (older loaders; 1.19.x normalizes automatically):

```jsonc
{
  "plugin": ["/absolute/path/to/integrations/opencode/echomind-memory"]
}
```

Configured local paths must be **directories**. OpenCode also discovers plugins
under `~/.config/opencode/plugins/` and `.opencode/plugins/`.

3. Keep the MCP tool surface (optional but recommended):

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

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `ECHOMIND_URL` | `http://127.0.0.1:8005` | EchoMind service base URL |
| `ECHOMIND_API_KEY` | — | sent as `X-API-Key` to hooks and MCP |
| `ECHOMIND_HOOK_PROJECT` | `basename(directory)` | project scope |
| `ECHOMIND_HOOK_USER` | EchoMind `default_user` | user scope |
| `ECHOMIND_HOOK_PROFILE` | `default` | profile scope |

## Behavior

- **Recall** is fetched once per user prompt and injected into the next model
  request as a `<echomind-memory>` system block (not persisted into history).
- **Store** runs on `session.idle` (per turn) and is **idempotent** via the last
  message id; the server also fingerprints the turn so compaction/session-end
  cannot duplicate it.
- **Compaction** stores the transcript being summarized; the server dedups it
  against the last idle turn.
- Hooks **fail open**: if EchoMind is down, the conversation continues with no
  memory injection.

## Version compatibility

| OpenCode | Plugin API | Status |
|---|---|---|
| 1.19.x (V1 loader) | `@opencode-ai/plugin` | Runtime-tested (local 1.19.5) |
| V2 (`@opencode/plugin` 2.x) | `Plugin.define`/`setup(ctx)` | Implemented + type-checked; runtime requires a V2-capable build |

The plugin has **no runtime dependency** on either plugin package: it
default-exports `{ id, setup, server }`, which both loaders understand. Install
`typescript` only if you want to run the type check:

```bash
npm install && npm run typecheck
```

## Privacy

Only user/assistant text is sent to the local EchoMind service. Tool output and
system rows are not stored by this plugin.
