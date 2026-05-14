[![OpenClaw Compatible](https://img.shields.io/badge/OpenClaw-Compatible-brightgreen)](https://github.com/OpenClaw)
[![Hermes-Agent Ready](https://img.shields.io/badge/Hermes--Agent-Ready-blue)](https://github.com/Hermes-Agent)
[![Claude Code Supported](https://img.shields.io/badge/Claude%20Code-Supported-orange)](https://claude.ai/code)
[![OpenCode Compatible](https://img.shields.io/badge/OpenCode-Compatible-red)](https://github.com/open-code-ai)


# EchoMind Skill —— 让你的 AI 拥有永久记忆与个人知识风格学习能力


🌐 **English Version:** [README.md](README.md)


> 支持 Hermes-Agent、OpenClaw、OpenCode、Claude Code 生态的长期记忆 Skill。
> 让你的 AI 不再"失忆"——记得你的偏好、研究方法、编码风格，甚至自我进化。

📦 **项目地址:** https://github.com/jasonatgit/echomind_memory.skill


---



### v1.0.8 新增功能

| 功能 | 说明 |
|------|------|
| **Hermes适配插件** | 实现 Hermes Agent记忆接口每轮自动存取。代码驱动，无需 LLM 决策，100% 可靠 |
| **平台感知记忆** | 所有上下文记忆打上平台标签（hermes/openclaw/opencode）；同平台权重 ×1.0，跨平台 ×0.5；用户偏好按平台隔离 |
| **WAL 并发模式** | 支持多进程并发读写 |
| **自动迁移** | 自动迁移 |
| **用户偏好按平台隔离** | 不同用户、不同应用、不同平台独立偏好，隔离你的记忆 |

---

## 支持框架

| 框架 | 支持方式 | 可靠性 |
|------|----------|--------|
| **Hermes-Agent** | MemoryProvider 插件 (自动) | ★★★★★ 100% |
| **OpenClaw** | `skill.yaml` + HTTP API 工具调用 | ★★★★☆ LLM 决策 |
| **OpenCode** | CLI + HTTP API 或 MCP stdio | ★★★★☆ LLM 决策 |
| **Claude Code** | MCP stdio 或 HTTP API | ★★★★☆ LLM 决策 |

---

## 核心能力

| 功能 | 说明 |
|------|------|
| **六类记忆系统** | Context / Task / User / Knowledge / Experience / Research |
| **强化学习自动优化** | 根据用户正/负反馈，AI 自动调整记忆权重，越用越聪明 |
| **研究方向记忆** | 记录论文元数据、理论模型、算法方法以及研究笔记 |
| **代码风格记忆** | 记录你是否喜欢 type hint、注释风格、函数长度 |
| **经验沉淀与复用** | 上次修复的问题 / 用过的算法模型 → 下次自动推荐 |
| **零依赖本地存储** | SQLite 持久化，无需 Docker / PostgreSQL / Redis |
| **跨框架兼容** | 独立于任何 LLM，适配 Hermes / OpenClaw / OpenCode / Claude Code |

*记忆系统专门针对**管理科学与工程**科研方向的记忆进行了优化。**其他学科均可定制优化**。*

### 自动检索触发

当查询涉及以下领域时，系统自动检索研究记忆：

| 领域 | 触发关键词 |
|------|-----------|
| 运筹学 | 线性规划, 整数规划, operations research |
| 供应链 | 供应链, 库存, 物流, supply chain |
| 决策分析 | 决策分析, 多准则, AHP |
| 最优化 | 优化, 最优, 梯度 |
| 仿真模拟 | 仿真, 蒙特卡洛, simulation |
| 博弈论 | 博弈论, 纳什均衡 |
| 预测 | 时间序列, forecasting |
| 项目管理 | 关键路径, project management |
| 排队论 | 排队论, queuing |

---

## 快速安装

### Hermes-Agent（推荐 — 100% 自动存取）

```bash
# 安装为 MemoryProvider 插件
cp -r echomind_memory.skill ~/.hermes/plugins/echomind/
hermes config set memory.provider echomind

# 启动 Hermes — EchoMind 自动初始化
hermes
```

**效果：** 每轮对话自动存入、自动检索。无需 LLM 决策，无需手动操作。

### OpenClaw / OpenCode / Claude Code（HTTP 模式）

```bash
# 安装依赖
pip install -r requirements.txt

# 启动 HTTP 服务
cd ~/.openclaw/skills/echomind-memory && python3 main.py
# 或
cd ~/.opencode/skills/echomind-memory && python3 main.py
```

服务运行在 `http://localhost:8005`，LLM 根据 skill 触发规则调用记忆工具。

### Python 快速上手

```python
import sys; sys.path.insert(0, '/path/to/echomind_memory.skill')
from core.memory_agent import MainMemoryAgent

agent = MainMemoryAgent()
agent.enable_persistence()

# 存储记忆（平台感知）
agent.store(
    user_id="alice",
    task_id="task-001",
    context=[{"role": "user", "content": "供应链协调有哪些常见模型"}],
    task_status="completed",
    success=True,
    platform="hermes",  # 或 "openclaw", "opencode"
)

# 检索记忆
result = agent.retrieve_for_task(
    task_context="供应链协调",
    user_id="alice",
    platform="hermes",
)
for m in result["retrieved_memories"]:
    print(f"[{m.source}] {m.content[:80]} (重要度={m.importance})")

# 记录反馈（RL 自我进化）
agent.record_feedback(
    user_id="alice",
    task_id="task-001",
    feedback="positive",
    retrieved_memories=result["retrieved_memories"],
)

agent.disable_persistence()
```

---

## API 端点（HTTP 模式）

| 方法 | 端点 | 说明 |
|------|------|------|
| `POST` | `/api/memory/retrieve` | 检索任务记忆（支持 `platform` 参数） |
| `POST` | `/api/memory/store` | 存储对话上下文（支持 `platform` 参数） |
| `POST` | `/api/memory/feedback` | 记录反馈用于 RL 优化 |
| `POST` | `/api/memory/sync-code` | 同步项目代码风格记忆 |
| `POST` | `/api/research/paper` | 添加研究论文 |
| `POST` | `/api/research/note` | 添加研究笔记 |
| `GET` | `/api/research/papers` | 列出研究论文 |
| `GET` | `/health` | 健康检查 |

---

## 数据存储

所有持久化数据存储在 `~/.echomind/memory.db`（SQLite 文件）。可随时备份或删除。

一个文件，7 张表，零基础设施。

---

## 项目结构

```
echomind_memory.skill/
├── core/                  ← 平台无关记忆引擎
│   ├── __init__.py
│   ├── memory_agent.py    ← 6 Agent + RL
│   ├── storage/
│   │   └── sqlite_store.py ← 7 表 SQLite（WAL 模式）
│   ├── models/            ← Pydantic 数据模型
│   └── learning/          ← RL 权重优化器
├── adapters/              ← 平台适配层
│   ├── hermes_provider.py ← Hermes MemoryProvider
│   └── http_api.py        ← FastAPI HTTP
├── main.py                ← 统一入口
├── plugin.yaml            ← Hermes 插件元数据
├── skill.yaml             ← OpenClaw 工具定义
├── example/               ← 各平台调用示例
├── code_format/           ← OpenCode CLI 集成
├── README.md              ← 英文版
├── README.zh-CN.md        ← 中文版（本文件）
└── doc/                   ← 文档与开发日志
```

---

## 愿景

AI 不是工具，是协作者。协作者不应该每次见面都"重新认识你"。

EchoMind 让你的 AI：

- 记得你的编码风格、偏好和习惯
- 记得你修复过的 bug 和尝试过的方法
- 记得你研究过的论文和理论模型
- 拥有 RL 驱动的自我优化权重系统，每次交互后越用越聪明

这不是一个插件，这是 AI 的多智能体记忆神经网络。