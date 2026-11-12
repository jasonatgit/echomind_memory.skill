# 客户端集成 — Hermes / Claude Code / OpenCode

> 本文的博客版本：[blog/echomind-client-integrations-article.md](../blog/echomind-client-integrations-article.md)。

EchoMind 提供两层记忆能力：

1. **MCP 工具**（始终可用）：`echomind_retrieve`、`echomind_store`、
   `echomind_search`、`echomind_feedback`、`echomind_reflect`、
   `echomind_query`、`echomind_delete`、`echomind_health`。
2. **自动记忆 Hook**（本文）：客户端轻量插件在会话开始/每轮提示时自动召回，
   在轮次结束时自动落库，无需模型主动调用工具。

Claude Code 与 OpenCode 通过本机 EchoMind HTTP 服务通信（默认 `http://127.0.0.1:8005`）；
Hermes 则以原生 MemoryProvider 在进程内集成。默认情况下记忆数据不离开本机，
详见 [PRIVACY.md](PRIVACY.md)（英文）。

```
客户端插件/Hook ──HTTP──> /api/hooks/{claude|opencode} ──> retrieve_for_task / store
        │                                                        │
        └── MCP 工具（显式调用）──────────────────────────────────┘
```

Hook 端点为 **fail-open**：EchoMind 未启动或负载异常时，客户端继续对话，轮次不会失败；
客户端侧等待有上限（召回 2–3 秒，落库 10 秒）。

---

## 三种客户端对比

| 客户端 | 接入方式 | 自动召回 | 自动落库 | 压缩前保留 | 版本 |
|---|---|---|---|---|---|
| **Hermes Agent** | 原生 MemoryProvider | ✅ `prefetch` | ✅ `sync_turn` | ✅ `on_pre_compress` | v0.23.1 |
| **Claude Code** | 插件 + Hooks | ✅ SessionStart / UserPromptSubmit | ✅ Stop / SessionEnd | ✅ PreCompact | 2.1.x |
| **OpenCode** | V1/V2 插件 | ✅ context hook | ✅ session.idle | ✅ compaction | 1.19.x |

## Hermes Agent（v0.23.1，原生支持）

Hermes 是 EchoMind 集成最深、也是最早支持的客户端：它不是通过 Hook 脚本，而是以 **MemoryProvider 插件**在 Hermes 的 agent 循环内直接工作。

### 工作方式

| 生命周期 | EchoMind 行为 |
|---|---|
| `initialize` | 建立/加载 SQLite，解析 `hermes_home` / `agent_identity`（profile）/ `default_user` / `project` |
| `prefetch`（每轮前） | 自动召回并注入相关记忆 |
| `sync_turn`（每轮后） | 自动落库本轮（`extract_knowledge=false`，避免逐轮知识污染） |
| `on_session_end` | 会话收尾落库 |
| `on_pre_compress` | 压缩前保留记忆 |
| 工具 | 8 个 `echomind_*` MCP 工具始终可用 |

### v0.23.1 适配要点（EchoMind v1.2.20）

- **MemoryProvider 子类**：兼容默认 in-process 与 `plugins.isolation: host`（父进程以子类代理）。
- **多 profile 隔离（#140058）**：每个 provider 实例持有独立 `ConfigManager` 与 `LLMClient`，同一 gateway 进程内多个 profile 的 endpoint / API key 不再互相覆盖。
- **上下文感知后台线程**：自动反思经 `spawn_context_thread`，保留 profile 的 `HERMES_HOME` 与 secret 作用域。
- **可选钩子**：`recall_status()`（召回指示）、`identity_signature()`（gateway 缓存失效）、`unavailable_reason()`。
- **身份溯源**：`turn_author`、`user_id_alt`、`gateway_session_key`、`chat_*` 写入 provenance（不重绑身份）。
- **LLM 自动同步**：读取 `model.default` / `model.base_url` / `model.provider` 与 `providers.<name>.*`，展开 `${ENV}`，仅接受 OpenAI 兼容 provider。
- **鉴权**：HTTP/MCP 支持 `ECHOMIND_API_KEY`；`hermes memory setup` 写入的 secret 会被正确读取。

### 安装 / 激活

```bash
# 1. 安装插件（或使用你的插件目录）
cp -r . ~/.hermes/plugins/echomind/

# 2. 启用为 Hermes 的记忆提供者
hermes config set memory.provider echomind

# 3. 若使用本机 HTTP 服务，重启
systemctl --user restart echomind.service
```

Hermes v0.20+ 也可通过 `register(ctx)` 自动发现；`initialize` 会收到 `hermes_home`、`agent_identity`、`user_id` 等作用域参数。

### 版本状态

- **v0.23.1**：已适配（EchoMind v1.2.20 完成）。
- 旧版本 Hermes：仍可运行；v0.23.x 的多 profile 隔离与新钩子需要 EchoMind v1.2.20+。
- Hermes 不经过 `/api/hooks/*`；这些端点仅服务 Claude Code / OpenCode。

## Claude Code（v2.1.x）

插件目录：[`integrations/claude-code/`](../integrations/claude-code/)

### 安装

```bash
# 1. 启动 EchoMind
python main.py            # 或: systemctl --user start echomind.service
curl http://127.0.0.1:8005/health

# 2. 以开发方式加载插件
claude --plugin-dir /path/to/echomind_memory.skill/integrations/claude-code
```

持久安装：将目录加入 Claude Code marketplace，或复制到插件目录后用 `/plugin` 启用。
Claude Code 2.1.275+ 可通过 marketplace 安装：

```
/plugin install echomind-memory --marketplace <owner>/<repo>
```

### Hook 映射

| 事件 | 传输 | 行为 |
|---|---|---|
| `SessionStart`（`startup`/`resume`/`clear`/`compact`/`fork`） | command（`scripts/echomind_hook.py`） | `POST /api/hooks/claude` → 记忆简报写入 `additionalContext` |
| `UserPromptSubmit` | command | 按提交的 prompt 召回 → `additionalContext` |
| `Stop` | command | 落库本轮（幂等） |
| `PreCompact`（`manual`/`auto`） | command | 压缩前落库 transcript 尾部 |
| `SessionEnd` | command | 兜底落库最后一轮 |

五个事件统一走同一个标准库脚本：脚本从 stdin 读取事件 JSON，读取
`ECHOMIND_URL` 与下面的身份变量后转发。单一传输让 URL、密钥与身份配置对
所有事件一致（hook JSON 的 `url` 字段无法读取客户端环境变量）。召回请求
上限 3 秒，落库请求上限 10 秒；脚本始终输出 JSON 并以 0 退出，记忆服务故障
不会使对话失败。

### 配置

| 环境变量 | 默认 | 含义 |
|---|---|---|
| `ECHOMIND_URL` | `http://127.0.0.1:8005` | 服务地址 |
| `ECHOMIND_API_KEY` | — | MCP 与 Hook 的 `X-API-Key` |
| `ECHOMIND_HOOK_PROJECT` | `basename(cwd)` | 项目作用域 |
| `ECHOMIND_HOOK_USER` | EchoMind `default_user` | 用户作用域 |
| `ECHOMIND_HOOK_PROFILE` | `default` | 分身作用域 |

### 验证

```bash
claude plugin validate integrations/claude-code
claude mcp list          # echomind 应可连接
# 会话内:
/hooks                   # 确认 SessionStart / UserPromptSubmit / Stop 已注册
```

Windows：所有 Hook 默认用 `python3`；若解释器是 `python`/`py`，请修改
`hooks/hooks.json` 的 `command`。

---

## OpenCode（1.19.x）

插件目录：[`integrations/opencode/echomind-memory/`](../integrations/opencode/echomind-memory/)

插件为 **V1/V2 双实现**：默认导出同时包含 V1 `server()` 与 V2 `setup(ctx)`，
且不运行时依赖任一插件包。

### 安装

```jsonc
// ~/.config/opencode/opencode.jsonc（OpenCode 1.19.x）
{
  "plugin": ["/absolute/path/to/integrations/opencode/echomind-memory"]
}
```

OpenCode 1.19.x 使用单数 `plugin` 键，元素为字符串路径（或
`[path, options]` 二元组）。本地插件路径必须是**目录**。OpenCode 也会自动发现
`~/.config/opencode/plugins/` 与 `.opencode/plugins/` 下的插件。

> `setup(ctx)` 的 V2 路径为实验性：V2 插件 API（`ctx.session.hook`、
> `ctx.event.subscribe({types})`）**未随 1.19.x 发布**，插件会检测并保持惰性。
> 1.19.x 不支持 `plugins` + `{package: ...}` 配置。

同时保留 MCP 工具：

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

### 行为

| 能力 | V1（`@opencode-ai/plugin`） | V2（`@opencode/plugin`） |
|---|---|---|
| 提示时召回 | `chat.message` | `session.hook("prompt")` |
| 注入上下文 | `experimental.chat.system.transform` | `session.hook("context")` |
| idle 落库 | `event` → `session.idle` | `ctx.event.subscribe({types:["session.idle"]})` |
| 压缩前保留 | `experimental.session.compacting` | `session.hook("compaction")` |

召回每条 prompt 只取一次（上限 2 秒），注入到下一次模型请求的
`<echomind-memory>` 块（不写入历史）。落库按轮次幂等（轮次键为最后一条消息
id）；每次 idle 只发送上次落库之后的新消息，压缩复用同一轮次键，因此不会写出
第二行。

### 版本状态

| OpenCode | 插件 API | 状态 |
|---|---|---|
| 1.19.x（V1 加载器） | `@opencode-ai/plugin` | 已运行时验证（1.19.5） |
| V2（`@opencode/plugin` 2.x） | `setup(ctx)` | 防御性惰性实现；1.19.x 无 V2 API |

`tsconfig.json` 较宽松且未依赖 `@opencode-ai/plugin`，因此
`npm run typecheck` 只是语法检查，不代表与真实 V2 API 的契约一致。

---

## 服务端 Hook 端点

> 这些端点仅供 Claude Code / OpenCode 使用。Hermes Agent 以原生 MemoryProvider 在进程内调用引擎 API，不经过 HTTP Hook。

### `POST /api/hooks/claude`

接收 Claude Code hook payload，返回 Claude 读取的 hook JSON：

```json
{
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "<echomind-memory>…</echomind-memory>"
  }
}
```

`Stop`/`PreCompact`/`SessionEnd` 返回 `{}`。

### `POST /api/hooks/opencode`

| action | 请求 | 响应 |
|---|---|---|
| `recall` | `{action, query, session_id, project, profile}` | `{"context": "...", "count": 3}` |
| `briefing` | `{action, session_id, project, profile}` | `{"context": "...", "count": 5}` |
| `store` | `{action, session_id, turn, messages, project, profile, extract_knowledge}` | `{"status": "stored\|duplicate\|empty\|error"}` |

配置 `server.api_key` 或 `ECHOMIND_API_KEY` 时，两个端点都要求 `X-API-Key`。
注入上限由 `hooks.max_context_chars` 控制（默认 8000）。

## 排障

| 现象 | 检查 |
|---|---|
| 无记忆注入 | `curl http://127.0.0.1:8005/health`；`claude --debug=hooks` / OpenCode 日志 |
| Hook/MCP 403 | 客户端环境是否导出了 `ECHOMIND_API_KEY` |
| 轮次重复 | 客户端是否稳定传 `session_id`/消息 id；服务端按轮次指纹去重 |
| Windows 上 Hook 无输出 | PATH 上无 `python3`，把 hook command 改为 `python` |
