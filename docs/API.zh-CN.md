## API 端点（HTTP 模式）

| 方法 | 端点 | 说明 |
|------|------|------|
| `POST` | `/api/memory/retrieve` | 检索任务记忆 |
| `POST` | `/api/memory/store` | 存储对话上下文 |
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
| `POST` | `/mcp` | MCP JSON-RPC 端点（远程；通知返回空 202） |
| `GET` | `/health` | 健康检查 |

> **错误语义（v1.2.13+）：** `DELETE /api/memory/{type}/{id}` 对未知记忆类型返回 **400**（此前 500）。`/api/reflect` 在达到用户每日反思限额时返回 **429**，解析失败/低置信度返回 **400**——失败反思会退还配额槽位，不消耗每日限额。

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
