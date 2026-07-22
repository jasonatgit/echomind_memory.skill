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
| `POST` | `/api/config/parameter` | 设置运行时配置参数 |
| `POST` | `/api/config/reload` | 从磁盘重载配置 |
| `POST` | `/api/reflect` | 自我反思 |
| `POST` | `/mcp` | MCP JSON-RPC 端点（远程） |
| `GET` | `/health` | 健康检查 |

---
