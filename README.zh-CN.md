[![OpenClaw Compatible](https://img.shields.io/badge/OpenClaw-Compatible-brightgreen)](https://github.com/OpenClaw)
[![Hermes-Agent Ready](https://img.shields.io/badge/Hermes--Agent-Ready-blue)](https://github.com/Hermes-Agent)
[![Claude Code Supported](https://img.shields.io/badge/Claude%20Code-Supported-orange)](https://claude.ai/code)
[![OpenCode Compatible](https://img.shields.io/badge/OpenCode-Compatible-red)](https://github.com/open-code-ai)

# EchoMind Skill —— 让你的 AI 拥有永久记忆与个人知识风格学习能力

🌐 **English Version:** [README.md](README.md)

> 全球首个支持 OpenClaw、Hermes-Agent、Claude Code (Cursor) 和 OpenCode 生态的长期记忆 Skill。
> 让你的 AI 不再"失忆"——记得你的偏好、研究方法、编码风格，甚至自我进化。

📦 项目地址
GitHub: https://github.com/jasonatgit/echomind_memory.skill
Star 它，让 AI 记得你。


### 新增功能

| 功能 | 说明 |
|------|------|
| **Hermes Agent记忆插件** | 实现 Hermes Agent记忆接口每轮自动存取。代码驱动，无需 LLM 决策，100% 可靠 |
| **平台感知记忆** | 所有上下文记忆打上标签（hermes/openclaw/opencode）；同平台权重不变，跨平台降低；用户偏好隔离 |
| **WAL 并发模式** | 支持多进程并发读写 |
| **自动迁移，新旧数据区隔** | 自动迁移，旧数据标记 |
| **用户偏好按平台隔离** | 不同平台(Openclaw)、Opencode等隔离记忆 |

---

## 版本更新

### v1.0.10 — Hermes v0.14.0 完整适配 (2026-05-17)

**新增 (MemoryProvider ABC 兼容):**

| 方法 | 说明 |
|------|------|
| `queue_prefetch()` | 兼容 Hermes v0.13.0+ 新增接口，消除每轮 AttributeError 日志 (was previously causing error logs on every turn) |
| `on_session_switch()` | 修复 `/resume` `/branch` `/reset` 操作后 session_id 混乱 (fixes session ID corruption after session switch operations) |
| `on_pre_compress()` | 上下文压缩前自动保存即将被丢弃的记忆 (auto-saves memories before context compression discards them) |
| `on_delegation()` | 子 agent 任务经验自动存入长期记忆 (captures sub-agent task experience into long-term memory) |

**修复:**

| 项目 | 说明 |
|------|------|
| `agent_context` 过滤 | 自动识别并跳过 `cron` / `subagent` / `flush` 等非主上下文，防止污染用户记忆 (auto-detects and skips non-primary contexts to prevent memory contamination) |
| `handle_tool_call` JSON | 工具调用返回值改为 JSON 字符串格式，符合 Hermes ABC 契约 (tool call returns now use JSON string format per Hermes ABC contract) |
| 写守卫统一 | `prefetch` / `sync_turn` / `on_session_end` / `on_memory_write` 统一使用 `skip_writes` 守卫 (all write methods now use unified skip_writes guard) |

### v1.0.9 — OpenClaw / OpenCode / Claude Code 三平台兼容修复 (2026-05-16)

| 修复项 | 影响平台 |
|--------|---------|
| `main.py` 新增 `call()` 调度函数 | OpenClaw |
| `http_api.py` retrieve/store 端点透传 `platform` 参数 | 全部平台 |
| `code_format/cli.py` 修复 async→sync 崩溃 | OpenCode |
| `skill.yaml` 新增 `platform` 参数 + `openclaw.call` 声明 | OpenClaw |

### v1.0.8 — 平台感知记忆 + Hermes 适配器 (2026-05-15)

- 平台感知记忆：同平台权重 ×1.0，跨平台 ×0.5
- Hermes Agent 插件：实现 MemoryProvider 接口，每轮自动存取
- WAL 并发模式 + 自动数据迁移



---

## 支持框架

| 框架 | 支持方式 |
|------|----------|
| **Hermes-Agent** | 通过 `call()` 通用接口 |
| **OpenClaw** | 通过 `skill.yaml` + `main.py` 工具调用 |
| **Claude Code (Cursor)** | 自动写入 `.echomind/` 文件，AI 自动读取上下文 |
| **OpenCode (Devika / CodeAct)** | 通过 CLI + JSON Schema 标准化记忆格式 |

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
| **跨框架兼容** | 独立于任何 LLM，适配 OpenClaw / Hermes / Claude Code / OpenCode |

*记忆系统专门针对**管理科学与工程**科研方向的记忆进行了优化，对查询的研究论文、理论模型、研究方法进行存储。**其他学科均可定制优化**。*

### 自动检索

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

### 一句话安装
在龙虾（OpenClaw）、Hermes-agent、opencode中直接说，或copy/paste：
```bash
安装EchoMind skills：https://github.com/jasonatgit/echomind_memory.skill
```

### 1. 安装

```bash
pip install -r requirements.txt
```

只需 3 个包：`pydantic` + `python-dotenv` + `numpy`，SQLite 是 Python 内置模块。

### 2. 整合进你的 AI Agent

#### OpenClaw / Hermes-Agent

把整个 `echomind_memory.skill/` 文件夹放入你的 `skills/` 目录下 —— 框架将自动加载所有工具。

框架通过 `skill.yaml` 发现工具定义，然后调用 `main.call(tool_name, **kwargs)` 完成调度。无需额外配置。

#### Claude Code / Cursor

在你的项目根目录运行同步命令：

```bash
python -m example.cursor_sync_example
```

或在代码中调用：

```python
from main import call
call("sync_code_memory", project_root="/path/to/project", user_id="alice")
```

自动生成两个文件供 AI 读取：

- `.echomind/context.json`：结构化偏好与经验
- `.echomind/README.md`：人类可读摘要

#### OpenCode

通过 CLI 获取标准化 JSON 记忆：

```bash
python -m example.opencode_call alice "供应链协调模型"
```

输出可直接注入 LLM prompt：

```python
memory = subprocess.check_output([
    "python", "-m", "example.opencode_call", user_id, query
], text=True, encoding="utf-8")
prompt += f"\n\n=== EchoMind Memory ===\n{memory}"
```

---

## 快速上手

```python
from main import call, init

# 初始化 SQLite 持久化（自动创建 ~/.echomind/memory.db）
init()

# 存储记忆
call("store_memory",
    user_id="alice",
    task_id="task-001",
    context=[{"role": "user", "content": "供应链协调有哪些常见模型"}],
    task_status="completed",
    success=True,
)

# 检索记忆
result = call("retrieve_memory", user_id="alice", query="供应链协调模型")
for m in result["working_memory"]:
    print(f"[{m['source']}] {m['content'][:80]}")

# 记录反馈（AI 自我进化）
call("record_feedback",
    user_id="alice",
    task_id="task-001",
    feedback="positive",
    retrieved_memories=result["working_memory"],
)
```

---

## 示例文件

| 文件 | 说明 |
|------|------|
| `example/hermes_call_example.py` | Hermes-Agent 完整使用示例 |
| `example/openclaw_call.py` | OpenClaw 完整使用示例（含 research 论文） |
| `example/cursor_sync_example.py` | Claude Code / Cursor 记忆同步示例 |
| `example/opencode_call.py` | OpenCode CLI 和 API 两种使用方式 |

---

## 数据存储

所有持久化数据存储在 `~/.echomind/memory.db`（SQLite 文件），可随时备份或删除。

---

## 架构

```
EchoMind Memory System (v1.0.10, 纯 SQLite)
├── User Memory       (偏好/习惯/RL 权重)     → user_memory 表
├── Task Memory       (任务状态/步骤)          → task_memory 表
├── Experience Memory (成功/失败经验)          → experience_memory 表
├── Context Memory    (对话上下文)             → context_memory 表
├── Knowledge Memory  (领域知识)               → knowledge_memory 表
├── Research Memory   (论文/笔记)             → research_papers + research_notes
└── RL Optimizer      (反馈自优化，权重持久化)
```

---

## 愿景

AI 不是工具，是协作者。协作者不应该每次见面都"重新认识你"。

EchoMind 让你的 AI：

- 记得你讨厌空行、喜欢 docstring
- 记得你修复过 auth.py 的 XSS 漏洞
- 记得你偏好用半参数模型而不是协方差建模
- 记得你曾因为某个模型因子痛苦了 3 小时 → 下次自动避开
- 这不是一个插件，这是 AI 的多智能体记忆神经网络