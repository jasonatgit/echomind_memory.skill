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

2. Point OpenCode at this plugin directory (V1 loader, the API shipped by
   OpenCode 1.19.x):

```jsonc
// ~/.config/opencode/opencode.jsonc
{
  "plugin": ["/absolute/path/to/integrations/opencode/echomind-memory"]
}
```

Configured local paths must be **directories**. OpenCode also discovers plugins
under `~/.config/opencode/plugins/` and `.opencode/plugins/`.

> V1 loads a local directory from a root `index.ts` (this 1.19.5 loader does not
> use `server.ts`); that file is the single implementation. V2 loads the same
> file through the package.json `exports` map. A re-export at the root is
> silently skipped by the V1 loader, so keep the implementation in `index.ts`.

> **V2 note:** a `setup(ctx)` path exists for a future `@opencode/plugin` V2
> API, but that API is **not present in OpenCode 1.19.x** (the installed
> `PluginInput` has no `session.hook`, and the config key is the singular
> `plugin`). The plugin detects the missing API and stays inert; do not use a
> `plugins`/`{package}` configuration on 1.19.x.

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
| `ECHOMIND_HOOK_PROJECT` | server `hooks.project` → `basename(cwd)` | project scope; sent only when set |
| `ECHOMIND_HOOK_USER` | EchoMind `default_user` | user scope |
| `ECHOMIND_HOOK_PROFILE` | `default` | profile scope |
| `ECHOMIND_DEBUG` | off | write diagnostics to the OpenCode log/console (debug level) |
| `ECHOMIND_TOAST` | off | real service failures show a 2-second warning toast, at most once per 10 minutes |

## Behavior

- **Recall** is fetched once per user prompt (2 s cap) and injected into the
  next model request as a `<echomind-memory>` system block (not persisted into
  history).
- **Store** runs on `session.idle` and sends only messages added since the last
  stored turn; the turn key is the last message id.
- **Compaction** sends only messages not yet stored, under the **same turn key**
  as the last idle, so the server dedupes it instead of writing a second row.
- Hooks **fail open**: if EchoMind is down or slow, the conversation continues
  without memory. The expected V1 fallback is **silent**; diagnostics go to the
  OpenCode log/console only when `ECHOMIND_DEBUG=1`. With `ECHOMIND_TOAST=1`,
  a real service failure shows one 2-second warning toast at most every 10
  minutes (the V1 fallback never toasts).

## Version compatibility

| OpenCode | Plugin API | Status |
|---|---|---|
| 1.19.x (V1 loader) | `@opencode-ai/plugin` | Runtime-tested (local 1.19.5) |
| V2 (`@opencode/plugin` 2.x) | `setup(ctx)` | Defensive, unverified: the V2 API is not shipped in 1.19.x, so `setup()` returns a no-op there |

The plugin has **no runtime dependency** on either plugin package: it
default-exports `{ id, setup, server }`. `tsconfig.json` is intentionally loose
(`strict:false`, no `@opencode-ai/plugin` types), so `npm run typecheck` is a
syntax check, not a contract check against the real API.

## Privacy

Only user/assistant text is sent to the local EchoMind service. Tool output and
system rows are not stored by this plugin.
