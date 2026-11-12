# 客户端集成 — Claude Code 与 OpenCode

> 本文的博客版本：[blog/echomind-client-integrations-article.md](../blog/echomind-client-integrations-article.md)。

EchoMind 提供两层记忆能力：

1. **MCP 工具**（始终可用）：`echomind_retrieve`、`echomind_store`、
   `echomind_search`、`echomind_feedback`、`echomind_reflect`、
   `echomind_query`、`echomind_delete`、`echomind_health`。
2. **自动记忆 Hook**（本文）：客户端轻量插件在会话开始/每轮提示时自动召回，
   在轮次结束时自动落库，无需模型主动调用工具。

两个客户端都只访问本机 EchoMind HTTP 服务（默认 `http://127.0.0.1:8005`）。
默认情况下记忆数据不离开本机，详见 [PRIVACY.md](PRIVACY.md)（英文）。

```
客户端插件/Hook ──HTTP──> /api/hooks/{claude|opencode} ──> retrieve_for_task / store
        │                                                        │
        └── MCP 工具（显式调用）──────────────────────────────────┘
```

Hook 端点为 **fail-open**：EchoMind 未启动或负载异常时，客户端继续对话，不阻塞用户。

---

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
| `SessionStart`（`startup`/`resume`/`clear`/`compact`/`fork`） | **command**（`scripts/echomind_hook.py`） | `POST /api/hooks/claude` → 记忆简报写入 `additionalContext` |
| `UserPromptSubmit` | **http** | 按提交的 prompt 召回 → `additionalContext` |
| `Stop` | **http** | 落库本轮（幂等） |
| `PreCompact`（`manual`/`auto`） | **http** | 压缩前落库 transcript 尾部 |
| `SessionEnd` | **http** | 兜底落库最后一轮 |

`SessionStart` 必须用 command：Claude Code 该事件只支持 `command`/`mcp_tool`，
且启动时 MCP 工具尚不可用。脚本仅用标准库，输出 Claude 读取的 hook JSON。

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

Windows：SessionStart 默认用 `python3`；若解释器是 `python`/`py`，请修改
`hooks/hooks.json` 的 `command`。

---

## OpenCode（1.19.x）

插件目录：[`integrations/opencode/echomind-memory/`](../integrations/opencode/echomind-memory/)

插件为 **V1/V2 双实现**：默认导出同时包含 V1 `server()` 与 V2 `setup(ctx)`，
且不运行时依赖任一插件包。

### 安装

```jsonc
// ~/.config/opencode/opencode.jsonc（V2 / 最新）
{
  "plugins": [
    { "package": "/absolute/path/to/integrations/opencode/echomind-memory" }
  ]
}
```

旧 V1 加载器使用单数键（1.19.x 会自动归一化）：

```jsonc
{
  "plugin": ["/absolute/path/to/integrations/opencode/echomind-memory"]
}
```

本地插件路径必须是**目录**。OpenCode 也会自动发现
`~/.config/opencode/plugins/` 与 `.opencode/plugins/` 下的插件。

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

召回每条 prompt 只取一次，注入到下一次模型请求的 `<echomind-memory>` system 块
（不写入历史）。落库按 message id 幂等；服务端再按轮次指纹去重，压缩不会重复。

### 版本状态

| OpenCode | 插件 API | 状态 |
|---|---|---|
| 1.19.x（V1 加载器） | `@opencode-ai/plugin` | 已运行时验证（1.19.5） |
| V2（`@opencode/plugin` 2.x） | `Plugin.define` / `setup(ctx)` | 已实现 + `tsc --noEmit`；运行时需 V2 build |

类型检查：

```bash
cd integrations/opencode/echomind-memory
npm install && npm run typecheck
```

---

## 服务端 Hook 端点

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
| Windows SessionStart 为空 | PATH 上无 `python3`，把 hook command 改为 `python` |
