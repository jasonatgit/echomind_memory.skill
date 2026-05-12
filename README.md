[![OpenClaw Compatible](https://img.shields.io/badge/OpenClaw-Compatible-brightgreen)](https://github.com/OpenClaw)
[![Hermes-Agent Ready](https://img.shields.io/badge/Hermes--Agent-Ready-blue)](https://github.com/Hermes-Agent)
[![Claude Code Supported](https://img.shields.io/badge/Claude%20Code-Supported-orange)](https://claude.ai/code)
[![OpenCode Compatible](https://img.shields.io/badge/OpenCode-Compatible-red)](https://github.com/open-code-ai)

# EchoMind Skill —— 让你的 AI 拥有永久记忆与个人知识风格学习能力

> 全球首个支持 OpenClaw、Hermes-Agent、Claude Code (Cursor) 和 OpenCode 生态的长期记忆 Skill。
> 让你的 AI 不再"失忆"——记得你的偏好、研究方法、编码风格，甚至自我进化。

📦 项目地址
GitHub: https://github.com/jasonatgit/echomind_memory.skill
Star 它，让 AI 记得你。

---

## 支持框架

| 框架 | 支持方式 |
|------|----------|
| **OpenClaw** | 通过 `skill.yaml` + `main.py` 工具调用 |
| **Hermes-Agent** | 通过 `call()` 通用接口 |
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
| **经验沉淀与复用** | 上次修复的问题 / 用过的模型 → 下次自动推荐 |
| **零依赖本地存储** | SQLite 持久化，无需 Docker / PostgreSQL / Redis |
| **跨框架兼容** | 独立于任何 LLM，适配 OpenClaw / Hermes / Claude Code / OpenCode |

*记忆系统专门针对管理科学与工程科研方向的记忆进行了优化，对查询的研究论文、理论模型、研究方法进行存储。其他学科均可定制优化。*

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
EchoMind Memory System
├── Context Memory    (对话上下文, 内存)
├── Task Memory       (任务状态, 内存)
├── User Memory       (用户偏好/习惯, 内存 + SQLite)
├── Knowledge Memory  (通用知识, 内存)
├── Experience Memory (经验总结, 内存 + SQLite)
└── Research Memory   (研究论文/笔记, 内存 + SQLite)
```

---

## 愿景

AI 不是工具，是协作者。协作者不应该每次见面都"重新认识你"。

EchoMind 让你的 AI：

- 记得你讨厌空行、喜欢 docstring
- 记得你修复过 auth.py 的 XSS 漏洞
- 记得你偏好用半参数模型而不是协方差建模
- 记得你曾因为某个因子痛苦了 3 小时 → 下次自动避开
- 这不是一个插件，这是 AI 的多智能体记忆神经网络。