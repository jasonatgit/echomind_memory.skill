## API 端点（HTTP 模式）

| 方法 | 端点 | 说明 |
|------|------|------|
| `POST` | `/api/memory/retrieve` | 检索任务记忆 |
| `POST` | `/api/memory/store` | 存储对话上下文 |
| `POST` | `/api/memory/query` | 结构化来源查询（project/tags/来源/日期谓词，无评分） |
| `POST` | `/api/memory/feedback` | 记录反馈用于 RL 优化 |
| `POST` | `/api/memory/sync-code` | 同步项目代码风格记忆 |
| `GET` | `/api/memory/search-sessions` | 搜索会话转录 |
| `GET` | `/api/memory/health` | 记忆健康报告（简报 + 状态 + flags） |
| `POST` | `/api/memory/{type}/{id}/state` | 设置记忆生命周期状态 |
| `POST` | `/api/memory/cleanup` | 基于 TTL 的记忆清理 |
| `DELETE` | `/api/memory/{type}/{id}` | 删除单条记忆 |
| `POST` | `/api/memory/delete-user` | 删除用户全部记忆 |
| `POST` | `/api/research/paper` | 添加研究论文 |
| `POST` | `/api/research/note` | 添加研究笔记 |
| `GET` | `/api/knowledge/{id}/evolution` | 查询知识演化链 |
| `GET` | `/api/config` | 读取当前配置 |
| `POST` | `/api/config/parameter` | 设置运行时配置参数（section 白名单；`api_key` 受保护） |
| `POST` | `/api/config/reload` | 从磁盘重载配置 |
| `POST` | `/api/reflect` | 自我反思 |
| `POST` | `/mcp` | MCP JSON-RPC 端点（远程；通知返回空 202）。配置 `server.api_key` 时与 `/api/*` 一样要求 `X-API-Key`（为空时开放） |
| `GET` | `/health` | 健康检查 |

> **错误语义（v1.2.13+）：** `DELETE /api/memory/{type}/{id}` 对未知记忆类型返回 **400**（此前 500）。`/api/reflect` 在达到用户每日反思限额时返回 **429**，解析失败/低置信度返回 **400**——失败反思会退还配额槽位，不消耗每日限额。

> **MCP 客户端身份（v1.2.15+）：** `initialize` 捕获的来源客户端按 HTTP 连接以 `Mcp-Session-Id` 头（或 `X-Session-Id`）隔离；`X-Client-Name` 可按请求设置。并发客户端不再互相串号。stdio 网关按进程归属（每连接一进程）。

---

## 关键请求参数

### POST /api/memory/retrieve
| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|:---:|------|------|
| `user_id` | string | ✅ | | 用户标识 |
| `query` | string | ✅ | | 检索查询 |
| `task_id` | string | | | 进行中任务 ID |
| `platform` | string | | | 平台标签（默认 `http`） |
| `max_results` | integer | | 5 | 最多返回的记忆条数（在 core 内生效） |
| `project` | string | | "default" | 项目隔离标识 |
| `session_id` | string | | "" | 会话标识 |
| `profile` | string | | "default" | 用户分身隔离 |
| `tags` | array | | [] | 标签过滤（大小写不敏感；默认 OR） |
| `tags_match_all` | boolean | | false | 设为 true 要求全部标签命中（AND） |
| `origin_platform` | string | | | 传输方式过滤（mcp/http/hermes/cli） |
| `origin_client` | string | | | 来源客户端过滤（claude-code/opencode/...） |

### POST /api/memory/store
| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|:---:|------|------|
| `user_id` | string | ✅ | | 用户标识 |
| `task_id` | string | ✅ | | 任务标识 |
| `context` | array | ✅ | | 对话消息（role/content 对） |
| `task_status` | string | ✅ | | completed / failed / pending |
| `success` | boolean | | false | 任务是否成功 |
| `experience_summary` | string | | | 快速摘要 |
| `platform` | string | | | 平台标签（默认 `http`） |
| `title` | string | | | 任务标题 |
| `project` | string | | "default" | 项目标识 |
| `session_id` | string | | "" | 会话标识 |
| `correction` | boolean | | false | 用户是否在纠正 agent |
| `profile` | string | | "default" | 用户分身 |
| `tags` | array | | [] | 调用方 tags（优先）；自动主题 tags 补足 |
| `origin_client` | string | | | 来源客户端（claude-code/opencode/...）；随记录来源信封落库 |
| `turn` | integer | | 0 | 来源会话中的轮次索引；记录到知识进化行的 `origin_turn`（v1.2.15） |

### POST /api/memory/query
结构化来源查询（v1.2.14）——精确来源谓词，**无相关性评分**。结果跨所选记忆表合并、按时间倒序。一天的记忆：`date_from` = `date_to` = `YYYY-MM-DD`。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|:---:|------|------|
| `user_id` | string | ✅ | | 用户标识 |
| `profile` | string | | "default" | 用户分身 |
| `memory_type` | string | | "all" | knowledge/experience/task/context/research/transcript/reflection，逗号分隔或 "all" |
| `project` | string | | | 项目作用域 |
| `tags` | array | | [] | 标签过滤（大小写不敏感） |
| `tags_match_all` | boolean | | false | 设为 true 要求全部标签命中（AND） |
| `origin_platform` | string | | | 传输方式过滤（mcp/http/hermes/cli） |
| `origin_client` | string | | | 来源客户端过滤 |
| `date_from` / `date_to` | string | | | 日期边界（含，YYYY-MM-DD） |
| `limit` | integer | | 20 | 最大返回条数 |

未知 `memory_type` 返回 **400**。每条结果含 `memory_type`、`id`、`content`、`tags`、`project`、`origin_platform`、`origin_client`、`created_at` 与完整来源 `envelope`。

### POST /api/reflect
| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|:---:|------|------|
| `user_id` | string | ✅ | | 用户标识 |
| `count` | integer | | 8 | 反思的最近记录数 |
| `platform` | string | | "http" | 平台标签 |
| `record_ids` | array | | | 指定反思的记录 ID |
| `llm_response` | string | | | Phase 2 的 LLM 响应（省略则返回 Phase 1 prompt） |
| `profile` | string | | "default" | 用户分身 |

---

## MCP 工具

MCP 协议暴露以下工具（经 `POST /mcp` 或 `mcp_gateway.py` stdio）：

| 工具 | 说明 |
|------|------|
| `echomind_retrieve` | 按查询语义检索长期记忆（支持 project/session_id/profile、tags、origin） |
| `echomind_store` | 存储交互入记忆（支持 project/session_id/profile、调用方 tags、origin_client、turn） |
| `echomind_search` | 按关键词搜索会话转录 |
| `echomind_feedback` | 对检索结果提供正/负反馈 |
| `echomind_reflect` | 触发反思（Phase 1 构建 prompt；Phase 2 带 llm_response 提交） |
| `echomind_query` | 按精确谓词的结构化来源查询：project、tags（OR/AND）、origin_client/origin_platform、日期区间、记忆类型——无相关性评分 |
| `echomind_delete` | 删除一条记忆 |
| `echomind_health` | 健康检查 |
