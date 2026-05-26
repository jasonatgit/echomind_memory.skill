<p align="center">
  <img src="assets/banner.png" alt="echomind_memory.skill" width="100%">
</p>

[![OpenClaw Compatible](https://img.shields.io/badge/OpenClaw-Compatible-brightgreen)](https://github.com/OpenClaw)
[![Hermes-Agent Ready](https://img.shields.io/badge/Hermes--Agent-Ready-blue)](https://github.com/Hermes-Agent)
[![Claude Code Supported](https://img.shields.io/badge/Claude%20Code-Supported-orange)](https://claude.ai/code)
[![OpenCode Compatible](https://img.shields.io/badge/OpenCode-Compatible-red)](https://github.com/open-code-ai)


# EchoMind Memory Skill —— 让你的 AI 拥有永久记忆与自我进化能力


🌐 **English Version:** [README.md](README.md)


> 支持 Hermes Agent、OpenClaw、OpenCode、Claude Code 生态的长期记忆 Skill。

> 让你的 AI 不再"失忆"——记得你的偏好、风格、研究方法，自我反思自我进化。

> EchoMind-Memory Skill帮助你：在对话中提取知识，在反思中沉淀规则。


📦 **项目地址:** https://github.com/jasonatgit/echomind_memory.skill



---


## EchoMind 核心十大能力

| 功能 | 说明 |
|------|------|
| **自我进化引擎 Agent** 🆕 | 自动从原始记忆中反思后提炼语义知识和程序化规则，零配置 LLM 注入 |
| **七类记忆系统** | User/ Task/ Experience/ Context/ Knowledge/ Research/ Reflection |
| **RL强化学习自动优化** | 根据用户正/负反馈，AI 自动调整记忆权重并且持久化，越用越聪明 |
| **Few-Shot锚定** | 小样本快速构建记忆规范，提升记忆质量 |
| **经验沉淀与复用** | 上次修复的问题 / 用过的算法模型 → 下次自动推荐 |
| **多重检索触发** | 关键词 + RL 权重 + LLM 语义，真正的“语义记忆系统” |
| **防幻觉污染** 🆕 | 长期记忆安全机制，置信度门控低的反思结果自动丢弃，防止幻觉污染记忆 |
| **平台感知记忆隔离**  | 跨平台权重衰减，用户、项目、会话、主题、研究领域统统隔离，记忆再也不会混乱 |
| **零依赖本地存储** | SQLite 持久化，无需 Docker / PostgreSQL / Redis |
| **跨框架兼容** | 独立于任何 LLM，适配 Hermes / OpenClaw / OpenCode / Claude Code |

---

### 自动检索触发
EchoMind 记忆系统专门针对*科研方向*的记忆进行了优化，对查询的研究论文、理论模型、研究方法等进行存储。

当查询涉及以下领域*关键词*或相关*语义*时，系统自动检索研究记忆：

| 领域  |
|------|
| 管理科学 |
| AI  |
| NLP  |
| 生物学  |
| 计算机  |
| 机器人  |
| 语音与音频  |
| 推荐系统  |
| 统计与决策  |

**其他学科与关键词均可定制优化**


---

## 支持框架

| 框架 | 支持方式 | 可靠性 |
|------|----------|--------|
| **Hermes-Agent** | MemoryProvider 插件 (自动) | ★★★★★ 100% |
| **OpenClaw** | `skill.yaml` + HTTP API 工具调用 | ★★★★☆ LLM 决策 |
| **OpenCode** | CLI + HTTP API 或 MCP stdio | ★★★★☆ LLM 决策 |
| **Claude Code** | MCP stdio 或 HTTP API | ★★★★☆ LLM 决策 |


---


## v1.1.0  新增功能

**核心要点：**
*引入**专用反思引擎 Agent**，从原始情景记忆(Episodic)中主动提炼语义记忆(Semantic)和程序性记忆(Procedural) 。类似人类"睡前反思"或 Reflexion/SRMA 架构。*

| 功能 | 说明 |
|------|------|
| **自我进化引擎 Agent** 🧠 | 从原始对话中自动提炼长期知识。自动触发**自我反思**，将原始交互记录蒸馏为持久化知识、用户偏好和程序化规则——实现记忆的真正自我进化 |
| **升级强化学习能力** | RL 权重Range模式，随机采样，用户反馈自动收敛 |
| **专业 Prompt 配置化** | 对专业领域实现Prompt配置化，无需改代码即可调优 |
| **置信度过滤** | 置信度低于阈值的反思结果自动丢弃，**防止幻觉污染记忆** |
| **记忆源追踪** | 根据完整存储反思记录，平台标签、来源追踪 |
| **重要性评分** | 对记忆重要性评分，沉淀有价值记忆 |
| **多重检索触发** | 关键词 + RL 权重 + LLM 语义，真正的“语义记忆系统” |
| **记忆隔离** | 用户、项目、会话、主题、研究领域统统隔离，记忆再也不会混乱 |
| **架构升级** | 全新反思引擎架构，支持高度灵活的Prompt配置化 |


---

## v1.1.0 版本学术参考

本次发行的 v1.1.0 的技术方案中Self-Reflective Agent部分设计受到以下研究的启发：

### 1、SAGE: Self-evolving Agents with Reflective and Memory-Augmented Abilities

Liang, X., He, Y., Xia, Y., Song, X., Wang, J., Tao, M., Sun, L., Yuan, X., Su, J., Li, K., Chen, J., Yang, J., Chen, S., & Shi, T. (2024).

- **论文地址：** [arXiv:2409.00872](https://arxiv.org/abs/2409.00872)
- **发表期刊：** *Neurocomputing* (2025)


### 2、SRMA: Self-Reflective Memory Consolidation in Agentic Architectures

Satya, P. R. B. (2026).

- **论文地址：** [IJCA Vol.187 No.73](https://www.ijcaonline.org/archives/volume187/number73/self-reflective-memory-consolidation-in-agentic-architectures/)
- **发表期刊：** *International Journal of Computer Applications*, 187(73)

---

## 致谢

We sincerely thank the authors of the above papers for their pioneering work on self-reflective memory mechanisms. Their research has provided valuable theoretical foundations and inspiration for the design of EchoMind-Memory.skill 's Self-Reflective Agent.

本项目 Self-Reflective Agent 的技术方案设计受益于上述开创性研究的启发，在此向论文作者致以诚挚的学术谢意。

同时，EchoMind-Memory.skill的 `自我进化` 与上述科学研究工作主要区别在于：采用**依赖反转**（核心引擎零 LLM 耦合）、**平台感知隔离**和**零配置部署**——使其可直接用于生产环境的 Multi-Agent 系统中，无需额外基础设施。这是一个产品级的智能体应用。



---

## 历史版本说明


### v1.0.10 — Hermes v0.14.0 完整适配 (2026-05-17)

**新增 (MemoryProvider ABC 兼容):**

| 方法 | 说明 |
|------|------|
| `queue_prefetch()` | 兼容 Hermes v0.13.0+ 新增接口，消除每轮 AttributeError 日志 (was previously causing error logs on every turn) |
| `on_session_switch()` | 修复 `/resume` `/branch` `/reset` 操作后 session_id 混乱 (fixes session ID corruption after session switch operations) |
| `on_pre_compress()` | 上下文压缩前自动保存即将被丢弃的记忆 (auto-saves memories before context compression discards them) |
| `on_delegation()` | 子 agent 任务经验自动存入长期记忆 (captures sub-agent task experience into long-term memory) |



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


## v1.0.8 已有功能

| 功能 | 说明 |
|------|------|
| **Hermes 适配插件** | 实现 Hermes Agent 记忆接口每轮自动存取。代码驱动，无需 LLM 决策，100% 可靠 |
| **平台感知记忆** | 所有上下文记忆打上平台标签（hermes/openclaw/opencode）；同平台权重 ×1.0，跨平台 ×0.5；用户偏好按平台隔离 |
| **WAL 并发模式** | 支持多进程并发读写 |
| **自动迁移** | 旧表结构自动迁移升级 |
| **用户偏好按平台隔离** | 不同用户、不同应用、不同平台独立偏好，隔离你的记忆 |







---

## 快速安装

### 一句话安装 (最快最简单)

在龙虾（OpenClaw）、Hermes-agent、opencode中直接说或copy/paste下面一句话：

```bash
安装EchoMind-Memory.skill并启动服务。下载地址：https://github.com/jasonatgit/echomind_memory.skill
```


### 1. 安装


### Hermes-Agent（推荐 — 100% 自动存取）

```bash
# 安装为 MemoryProvider 插件
cp -r echomind_memory.skill ~/.hermes/plugins/echomind/
hermes config set memory.provider echomind

# 启动 Hermes — EchoMind 自动初始化
hermes
```

**效果：** 每轮对话自动存入、自动检索。无需 LLM 决策，无需手动操作。对话后自动触发自我反思——无需任何额外配置。

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
from main import call

# 存储记忆（平台感知）
call("store_memory",
    user_id="alice",
    platform="hermes",
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

# 触发自我反思（v1.1.0）— Hermes 适配器自动调用
# 或通过 HTTP 手动触发：POST /api/reflect
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
| `POST` | `/api/reflect` 🆕 | 自我反思 |
| `GET` | `/health` | 健康检查 |

---

## 数据存储

所有持久化数据存储在 `~/.echomind/memory.db`（SQLite 文件）。可随时备份或删除。可通过 echomind_config.yaml 中的 storage.db_path 自定义存储路径。




---

## 愿景

AI 不是工具，是协作者。协作者不应该每次见面都"重新认识你"。

EchoMind 让你的 AI：

- 记得你的编码风格、偏好和习惯
- 记得你修复过的 bug 和尝试过的方法
- 记得你研究过的论文和理论模型
- 拥有 RL 驱动的自我优化权重系统，每次交互后越用越聪明
- 这不是一个插件，这是具有*自我反思记忆*的*AI 多智能体记忆神经网络*。