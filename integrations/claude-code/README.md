# EchoMind Memory — Claude Code plugin

Automatic long-term memory for Claude Code (v2.1.x):

- **SessionStart** → injects a compact memory briefing (`additionalContext`)
- **UserPromptSubmit** → recalls memory relevant to the prompt
- **Stop** → stores the completed turn (idempotent per turn)
- **PreCompact** → stores the transcript tail before compaction
- **SessionEnd** → stores the last turn as a fallback
- Keeps the full EchoMind MCP tool surface (8 tools) available to Claude

Requires the EchoMind HTTP service to be running (default `http://127.0.0.1:8005`).

## Install

1. Start EchoMind:

   ```bash
   python main.py            # or: systemctl --user start echomind.service
   curl http://127.0.0.1:8005/health
   ```

2. Load the plugin for a session (development):

   ```bash
   claude --plugin-dir /path/to/echomind_memory.skill/integrations/claude-code
   ```

   For a persistent install, copy this directory into your Claude Code plugins
   location and enable it with `/plugin` (or ship it through a marketplace).
   On Claude Code 2.1.275+, install from a marketplace with:

   ```
   /plugin install echomind-memory --marketplace <owner>/<repo>
   ```

3. Optional auth: set `ECHOMIND_API_KEY` in the environment Claude Code runs in.
   The MCP entry and every hook (they all run through `scripts/echomind_hook.py`)
   read it.

## Verify

```bash
claude plugin validate /path/to/integrations/claude-code
claude mcp list          # echomind should connect
# inside a session:
/hooks                   # confirm SessionStart / UserPromptSubmit / Stop are registered
```

Ask Claude a question that references an earlier session; the injected
`<echomind-memory>` block should appear in the debug log (`--debug=hooks`).

## Hook mapping

| Event | Transport | Behavior |
|---|---|---|
| `SessionStart` (`startup`/`resume`/`clear`/`compact`/`fork`) | command | `scripts/echomind_hook.py` → `POST /api/hooks/claude` → briefing |
| `UserPromptSubmit` | command | recall for the submitted prompt |
| `Stop` | command | store the completed turn (`extract_knowledge=false`) |
| `PreCompact` (`manual`/`auto`) | command | store the transcript tail |
| `SessionEnd` | command | store the last turn (fallback) |

All five events run the same stdlib script: it reads the event JSON from stdin,
so `ECHOMIND_URL`, `ECHOMIND_API_KEY` and the identity overrides apply uniformly.
Recall waits are capped at 3 s and store waits at 10 s.

## Configuration

- `ECHOMIND_URL` — service base URL (default `http://127.0.0.1:8005`)
- `ECHOMIND_API_KEY` — optional `X-API-Key`
- `ECHOMIND_HOOK_PROJECT` — override the project scope (default: basename of `cwd`)
- `ECHOMIND_HOOK_USER` — override the user scope (default: EchoMind `default_user`)
- `ECHOMIND_HOOK_PROFILE` — override the profile (default `default`)

Windows note: `hooks/hooks.json` runs every hook with `python3`.
If your interpreter is `python`/`py`, edit the hook `command`s.

## Privacy

Hooks send only user/assistant text to your local EchoMind service. Tool
outputs, system rows and tool-use blocks are dropped before storage. Context
injected into the model is hard-capped at 8,000 characters.
