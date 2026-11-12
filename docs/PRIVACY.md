# Privacy

EchoMind is a **local-first** memory engine. By default all memory data stays on
the machine where the service runs.

## What is stored

- Memory records you or your agent explicitly store (knowledge, preferences,
  experience, tasks, session context).
- Text the Claude Code / OpenCode integration hooks send to the local EchoMind
  HTTP service:
  - Claude Code: user/assistant text from the session transcript and the
    submitted prompt.
  - OpenCode: user/assistant text from the session and the submitted prompt.
- The integration hooks do **not** store tool output, system rows or tool-use
  blocks.

Data is written to the SQLite database at `db.path` (default
`~/.echomind/memory.db`).

## Where it goes

- The HTTP service binds to `127.0.0.1` by default.
- Hook payloads go to the local EchoMind service only.
- If you configure an LLM endpoint for reflection/semantic scoring, the text
  needed for that operation is sent to the endpoint **you configured**. EchoMind
  does not send memory anywhere else.

## Authentication

If `server.api_key` or `ECHOMIND_API_KEY` is configured, the HTTP API, MCP
endpoint and hook endpoints require the matching `X-API-Key` header.

## Deletion

- `DELETE /api/memory/{type}/{id}` deletes a single record.
- `POST /api/memory/delete-user` deletes a user's records (optionally scoped to
  one profile).
- `POST /api/memory/cleanup` applies the configured TTLs.
- Deleting the SQLite database file removes everything.

## Claude Code plugin / OpenCode plugin

The client plugins are thin adapters. They send only the text described above to
`http://127.0.0.1:8005` (configurable via `ECHOMIND_URL`) and hard-cap the
injected context (8,000 characters by default).

Questions: open an issue at
<https://github.com/jasonatgit/echomind_memory.skill/issues>.
