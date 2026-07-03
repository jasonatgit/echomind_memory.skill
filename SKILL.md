---
name: echomind-memory
version: "1.2.2"
description: EchoMind Memory — AI 持久记忆系统。支持 Hermes、OpenCode、OpenClaw、Claude Code 等多平台。9 张 SQLite 表覆盖 6 种记忆类型 + Self-Reflective Agent。
category: software-development
platforms:
  - hermes
  - opencode
  - openclaw
  - claude-code
tags:
  - ai-memory
  - long-term-memory
  - rl-optimization
  - sqlite
  - self-reflection
---

# EchoMind Memory v1.2.2

## 概述

EchoMind Memory 是一个纯 SQLite 的 AI 持久记忆系统，无需 PostgreSQL/Redis/ChromaDB。v1.1.0 新增 **Self-Reflective Agent**，从 Episodic 记录自动提炼 Semantic 知识和 Procedural 规则。服务运行在 `http://localhost:8005`。

### 6 种记忆类型

| 记忆类型 | API 来源 | 存储位置 | 检索方式 |
|---------|---------|---------|---------|
| **User** | 偏好、习惯、交互历史 | `user_memory` 表 | 总是检索 |
| **Task** | 任务状态、步骤 | `task_memory` 表 | has_history 时 |
| **Experience** | 成功/失败经验 | `experience_memory` 表 | is_complex 时 |
| **Context** | 对话上下文 | `context_memory` 表 | 总是检索（最近 2 会话） |
| **Knowledge** | 领域知识 | `knowledge_memory` 表 | requires_knowledge 时 |
| **Research** | 论文、阅读笔记 | `research_papers` + `research_notes` | requires_research 时 |

### RL 自优化

用户反馈（👍/👎）通过 RL 权重优化器调整检索重要性权重。权重持久化到 `user_memory.preferences.rl_weights`，重启后自动恢复。

### Self-Reflective Agent (v1.1.0)

从 Episodic 记忆自动提炼长期知识，实现记忆自我进化。

- **触发**：每 N 次 store 自动标记 `_pending_reflection`
- **Hermes**：`on_session_end` 自动调 `localhost:9119` → 用户已配 LLM → 零配置
- **HTTP**：`POST /api/reflect` 端点，调用方自己的 LLM 处理 prompt
- **输出**：key_insights → knowledge_memory / preferences → user_memory / rules → procedural
- **安全**：confidence < 0.6 自动丢弃，失败静默降级

## 平台集成

### Hermes Agent

```python
# 安装后 Hermes 自动发现 skill.yaml 中的工具定义
# 在对话中直接调用 retrieve_memory / store_memory / record_feedback
```

### OpenCode

```bash
# CLI 工具
python3 code_format/cli.py read jason my-project
python3 code_format/cli.py write jason my-project context.json
```

### OpenClaw

OpenClaw 通过 SKILL.md 指令驱动，agent 直接调用 HTTP API 端点：

```bash
# 启动服务
python main.py
# → http://localhost:8005
# Agent 通过 POST /api/memory/retrieve 和 POST /api/memory/store 进行记忆存取
```

### Claude Code (Cursor)

```bash
# 同步代码记忆到项目目录
POST /api/memory/sync-code {"project_root": "/path/to/project", "user_id": "alice"}
# → 生成 .echomind/ 目录供 Cursor 读取
```

## API 端点

所有端点返回 JSON。

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/api/memory/retrieve` | 检索记忆 |
| POST | `/api/memory/store` | 存储交互结果 |
| POST | `/api/memory/feedback` | 记录用户反馈 |
| POST | `/api/memory/sync-code` | 同步到项目 .echomind/ |
| GET | `/api/memory/search-sessions` | 搜索会话转录 |
| GET | `/api/memory/health` | 记忆健康报告 |
| POST | `/api/memory/{type}/{id}/state` | 设置记忆状态 |
| DELETE | `/api/memory/{type}/{id}` | 删除单条记忆 |
| POST | `/api/research/paper` | 添加研究论文 |
| POST | `/api/research/note` | 添加研究笔记 |
| POST | `/api/reflect` | 反思：build prompt / process result |
| GET | `/api/knowledge/{id}/evolution` | 查询知识演化链 |
| POST | `/mcp` | MCP JSON-RPC 端点 |

### 检索请求

```json
POST /api/memory/retrieve
{
  "user_id": "alice",
  "query": "如何优化查询性能？",
  "task_id": "task-001",        // 可选
  "max_results": 5              // 默认 5
}
```

返回 `working_memory` 数组（按重要性排序），含 `source`、`content`、`importance`、`metadata`。

### 存储请求

```json
POST /api/memory/store
{
  "user_id": "alice",
  "task_id": "task-001",
  "context": [
    {"role": "user", "content": "如何优化？"},
    {"role": "assistant", "content": "建议加缓存..."}
  ],
  "task_status": "completed",
  "success": true,
  "experience_summary": "通过添加 Redis 缓存降低响应时间"  // 可选
}
```

## 配置化支持 (v1.1.0)

EchoMind v1.1.0 支持通过 `echomind_config.yaml` 配置文件调整所有参数：

- **文件位置**: 优先级 `./echomind_config.yaml` > `~/.echomind/echomind_config.yaml` > 内置 `FALLBACK_CONFIG`
- **环境变量**: 可通过 `ECHOMIND_CONFIG=/path/to/config.yaml` 指定配置路径
- **Prompt 模板**: 内置引擎生成（无需配置）
- **检索参数**: 全部 9 项可调
- **领域检测**: 通过配置文件切换知识领域（支持 zh/en 关键词）
- **API 动态管理**: `POST /api/config/parameter` 运行时修改，`GET /api/config` 查看当前配置

### 45 领域支持 (v1.1.0)

echomind_config.yaml 内置 45 个知识领域，覆盖：运筹学、供应链、决策分析、AI、计算机科学、NLP、CV、机器人、推荐系统、生物学等。领域关键词支持中英文，自动从配置匹配。

## 项目文件结构

```
├── SKILL.md              ← 本文件（AI 助手加载入口）
├── skill.yaml            ← 技能元数据 + OpenClaw 工具定义
├── main.py               ← FastAPI 服务入口 + `call()` 统一调度
├── echomind_config.yaml          ← 全量默认配置
├── requirements.txt
├── core/                  ← 跨框架记忆引擎（核心）
│   ├── memory_agent.py    ← 6 Agent + RL + ReflectiveAgent
│   ├── reflective_agent.py ← Self-Reflective Agent (v1.1.0)
│   ├── storage/
│   │   ├── __init__.py
│   │   └── sqlite_store.py ← 存储层 9 张表 (WAL)
│   ├── models/
│   │   ├── context.py, task.py, user.py
│   │   ├── knowledge.py, experience.py
│   │   ├── research.py
│   │   └── reflection.py
│   └── learning/
│       └── rl_weight_optimizer.py
├── adapters/              ← 平台适配层
│   ├── hermes_provider.py ← Hermes MemoryProvider
│   └── http_api.py        ← FastAPI HTTP (OpenClaw/OpenCode)
├── code_format/           ← OpenCode CLI 集成
├── example/               ← 各平台调用示例
├── plugin.yaml            ← Hermes 插件元数据
```

## 部署

### 依赖与数据库

- **依赖**: `pydantic>=2.7`, `python-dotenv>=1.0`, `numpy>=1.26`, `PyYAML>=6.0`
- **数据库**: `~/.echomind/memory.db`（可在 `echomind_config.yaml` 中修改），9 张表自动创建

### Hermes Agent（推荐 — 100% 自动存取）

```bash
# 安装
cp -r echomind_memory.skill ~/.hermes/plugins/echomind/
hermes config set memory.provider echomind

# 启动 Hermes 即自动运行，无需手动操作
hermes
```

效果：Hermes 的 agent_loop 每轮之前自动 `prefetch()` 检索记忆，每轮之后自动 `sync_turn()` 存储。LLM 不需要决策，100% 可靠。

### OpenClaw / OpenCode / Claude Code（HTTP 模式）

```bash
python3 main.py              # 启动 FastAPI 服务 (port 8005)
```

LLM 通过 tool 调用 HTTP API，依赖 SKILL.md 触发规则。

### Platform-aware 记忆

所有记忆带平台标签存储。检索时同平台记忆权重 ×1.0，跨平台 ×0.5。用户偏好按平台隔离，`_default` 键为公共基础。

## 已知限制

- `knowledge_memory` 依赖关键词匹配（9 个预设领域），通用任务不创建知识条目
- `/mnt/d/` Windows 路径下 uvicorn 后台不稳定，建议在 WSL 原生路径运行
- context_memory 只在 store 时写入，未调用 store 时为空白