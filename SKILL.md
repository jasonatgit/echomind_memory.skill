---
name: echomind-memory
version: 1.0.10
description: EchoMind Memory — AI 持久记忆系统。支持 Hermes、OpenCode、OpenClaw、Claude Code 等多平台。7 张 SQLite 表覆盖 6 种记忆类型。
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
---

# EchoMind Memory v1.0.10

## 概述

EchoMind Memory 是一个纯 SQLite 的 AI 持久记忆系统，无需 PostgreSQL/Redis/ChromaDB。服务运行在 `http://localhost:8005`。

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

```python
# Python SDK 调用
from main import call
result = await call("retrieve_memory", user_id="alice", query="评估风险...")
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
| POST | `/api/research/paper` | 添加研究论文 |
| POST | `/api/research/note` | 添加研究笔记 |

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

## 部署

### 依赖

仅 3 个：`pydantic>=2.7`, `python-dotenv>=1.0`, `numpy>=1.26`

### 启动

```bash
cd ~/.hermes/skills/echomind-memory
python3 -c "
from main import app, memory_agent
import uvicorn
memory_agent.enable_persistence()
uvicorn.run(app, host='0.0.0.0', port=8005, log_level='error')
" &
```

### 数据库

- 路径：`~/.echomind/memory.db`（可在 `config.example.yaml` 中修改）
- 7 张表自动创建，无需手动初始化

## 项目文件结构

```
├── SKILL.md              ← 本文件（AI 助手加载入口）
├── skill.yaml            ← 技能元数据 + OpenClaw 工具定义
├── main.py               ← FastAPI 服务入口
├── memory_agent.py       ← 核心逻辑（6 个 Agent + RL）
├── storage/
│   ├── __init__.py
│   └── sqlite_store.py   ← SQLite 持久化层
├── models/               ← Pydantic 数据模型
│   ├── user.py
│   ├── task.py
│   ├── experience.py
│   ├── context.py
│   ├── knowledge.py
│   └── research.py
├── learning/
│   └── rl_weight_optimizer.py
├── core/                  ← 平台无关记忆引擎
│   ├── __init__.py
│   ├── memory_agent.py    ← 6 Agent + RL
│   ├── storage/
│   │   ├── __init__.py
│   │   └── sqlite_store.py ← 7 表 SQLite (WAL)
│   ├── models/
│   │   ├── context.py, task.py, user.py
│   │   ├── knowledge.py, experience.py
│   │   └── research.py
│   └── learning/
│       └── rl_weight_optimizer.py
├── adapters/              ← 平台适配层
│   ├── hermes_provider.py ← Hermes MemoryProvider (sync_turn 自动)
│   └── http_api.py        ← FastAPI HTTP (OpenClaw/OpenCode)
├── code_format/           ← OpenCode CLI 集成
├── example/               ← 各平台调用示例
├── config.example.yaml
├── main.py                ← 统一入口
├── plugin.yaml            ← Hermes 插件元数据
├── skill.yaml             ← OpenClaw 工具定义
├── SKILL.md               ← 本文件
└── requirements.txt
```

## 部署

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