<p align="center">
  <img src="assets/banner.jpg" alt="echomind_memory.skill" width="100%">
</p>

[![OpenClaw Compatible](https://img.shields.io/badge/OpenClaw-Compatible-brightgreen)](https://github.com/OpenClaw)
[![Hermes-Agent Ready](https://img.shields.io/badge/Hermes--Agent-Ready-blue)](https://github.com/Hermes-Agent)
[![Claude Code Supported](https://img.shields.io/badge/Claude%20Code-Supported-orange)](https://claude.ai/code)
[![OpenCode Compatible](https://img.shields.io/badge/OpenCode-Compatible-red)](https://github.com/open-code-ai)


# EchoMind Memory Engine —— 让你的 AI 拥有永久记忆与自我进化能力


🌐 **English Version:** [README.md](README.md)


> 支持 Hermes Agent、OpenClaw、OpenCode、Claude Code 等智能体的长期记忆引擎。

> 让你的 AI 不再"失忆"——记得你的偏好、风格、研究方法，自我反思自我进化。

> EchoMind Memory Engine 帮助你：在对话中提取知识，在反思中沉淀规则。


📦 **项目地址:** https://github.com/jasonatgit/echomind_memory.skill



---


## 🧠 EchoMind 核心能力

### 基础架构
| 功能 | 说明 |
|------|------|
| **七类记忆系统** | User / Task / Experience / Context / Knowledge / Research / Reflection |
| **零依赖本地存储** | SQLite 单文件数据库，无需 Docker / PostgreSQL / Redis |
| **结构化迁移 + 事务写入** | 结构化迁移列表 + 事务回滚；store() 一次性包裹 5 次保存 |

### 记忆智能（反思推理）
| 功能 | 说明 |
|------|------|
| **自我进化引擎 Agent** | 自动从原始记忆中提炼语义知识和程序化规则，零配置 LLM 注入；低置信度反思自动丢弃防止幻觉污染 |
| **Ebbinghaus遗忘曲线** | 覆盖全部 6 种记忆类型，自动降权或排除冷数据 |
| **记忆生命周期状态机** | Active → Stale → Archived → Superseded 全状态追踪，基于新鲜度自动转换 |
| **知识演化追踪** | 取代/丰富/确认/挑战四种关系 — Jaccard + LLM 混合检测 |
| **Flags 标记系统** | 自动检测 needs_verification 和 contradiction 的知识条目 |
| **记忆健康报告** | 按类型+状态聚合统计 + 7天增长 + Flags 摘要 |
| **实体抽取** | LLM 优先 + 关键词兜底（技术/概念实体） |
| **经验沉淀与复用** | 上次修复的问题 / 用过的算法模型 → 下次自动推荐 |
| **认知模式分类** | 每条知识携带 epistemic_mode（user_provided / reasoned / fuzzy / referenced）— 区分用户真实事实与 LLM 生成推理，写入时自动判定（零 LLM 成本） |
| **自我反思评分与诊断** | 四标准成熟度模型自评（情境觉察、架构一致性、从架构分析、整合与扩展）；实时系统健康注入智能体上下文 |
| **知识溯源追踪** | knowledge_evolution 中存储溯源链（origin_agent、origin_session_id、origin_turn），实现记忆供应链审计 |
| **Markdown 记忆档案** | `export_memory_to_markdown()` 生成完整 9 节 .md 文档（健康/画像/知识按认知模式分区/经验/任务/上下文/研究/反思/自我反思评分）；零新依赖 |
| **紧凑注入层** | `<memory-context>` 紧凑 Markdown 块为 LLM 上下文注入（Hermes v0.20+ 兼容） |
| **Hermes v0.20+ 适配** | 根 `register(ctx)` 入口 + `plugin.yaml` `kind: exclusive` — 兼容 Hermes v0.13–v0.20 |

### 检索与优化（RL强化自学习）
| 功能 | 说明 |
|------|------|
| **RL强化学习自动优化** | 根据用户正/负反馈自动调整权重并持久化；余弦学习率衰减 + epsilon-greedy 探索 |
| **多重检索触发** | 关键词 + RL 权重 + LLM 语义 — 真正的"语义记忆系统" |
| **自适应反思批处理** | 基于周活跃度动态调整反思触发阈值 |
| **Few-Shot 锚定** | 小样本快速构建记忆规范，提升记忆质量 |

### 用户理解
| 功能 | 说明 |
|------|------|
| **6 类偏好推理** | code_style / response_style / platform / language / depth / tone |
| **用户纠正信号检测** | 中英文关键词匹配纠正信号，触发即时反思 |
| **会话隔离上下文管理** | 每 session_id 独立上下文窗口，LRU 淘汰 + 消息归档 |

### 平台与集成
| 功能 | 说明 |
|------|------|
| **跨框架兼容** | 独立于 LLM，适配 Hermes / OpenClaw / OpenCode / Claude Code |
| **平台感知记忆隔离** | 同平台 ×1.0，跨平台 ×0.5；按用户/项目/会话/主题/领域隔离 |
| **双传输 MCP 网关** | stdio + Streamable HTTP；7 个原生 Claude Code 工具 |
| **记忆 CRUD API** | DELETE 单条/全用户 + TTL 自动清理 |
| **Hermes Agent 深度集成** | MemoryProvider 各版本兼容，每轮自动存取，零 LLM 决策 |

---

### 自动检索触发
EchoMind 记忆系统专门针对*科研方向*的记忆进行了优化，对查询的研究论文、理论模型、研究方法等进行存储。

当查询涉及以下领域*关键词*或相关*语义*时，系统自动检索研究记忆：管理科学、AI、NLP、生物学、计算机、机器人、语音与音频、推荐系统、统计与决策。
*其他学科与关键词均可定制优化*


---

## 🔌  支持框架

| 框架 | 支持方式 | 可靠性 |
|------|----------|--------|
| **Hermes-Agent** | MemoryProvider 插件 (自动, v0.13.0–v0.20.0) | ★★★★★ 100% |
| **OpenClaw** | `skill.yaml` + HTTP API 工具调用 | ★★★★☆ LLM 决策 |
| **OpenCode** | CLI + HTTP API 或 MCP stdio | ★★★★☆ LLM 决策 |
| **Claude Code** | MCP stdio 或 HTTP API | ★★★★☆ LLM 决策 |


---



## 📝 博客

| 日期 | 标题 |
|:-----|:------|
| 2026-08 | 🧠[EchoMind: Markdown 呈现：让 AI 记忆从"黑盒"变为"可读文档"](blog/echomind-markdown-rendering-article.md) |
| 2026-08 | 🎯[ 在"模型军备竞赛"的火线上，老梁的DSH 的插件化是一场豪赌还是一次押对？](blog/dsh-evolution-analysis.md) |
| 2026-08 | 🪞 [EchoMind：自我反思-引导 AI 记忆思考自身](blog/echomind-autoreflection-article-zh.md) |
| 2026-07 | 🪞 [Echomind: Self-Reflective Agent 上篇 —— 反思引擎与记忆生命周期](blog/echomind-reflective-agent-part1-article.md) |
| 2026-07 | 🪞 [Echomind: Self-Reflective Agent 下篇 —— 知识演化与记忆治理](blog/echomind-reflective-agent-part2-article.md) |
| 2026-06 | 🎯[Echomind: RL 强化自学习的记忆系统](blog/echomind-rl-article.md) |
| 2026-05 | 🧠[Memory Engine：为什么每个 AI 智能体都需要一个记忆系统](blog/echomind-agent-memory-article.md) |

*部分内容含AI创作*


---


## 📜 版本历史

| 版本 | 核心要点 |
|:--------|:-----------|
| v1.2.9 | *Markdown 记忆档案（9 节 .md）、Hermes v0.20 适配、认知位置生命周期。* |
| v1.2.8 | *自我反思进化：认知状态分类、溯源追踪、架构自诊断。* |
| v1.2.7 | *深度代码审查：42 项 bug 修复与 48 项回归测试。* |
| v1.2.3 | *RL advantage baseline、RCW 源权重分配、知识多样性、profile 导出。* |
| v1.2.2 | *记忆生命周期管理、知识演化追踪、实体抽取、Streamable HTTP MCP。* |
| v1.2.0 | *MCP stdio 网关、艾宾浩斯遗忘曲线、会话隔离、记忆 CRUD。* |
| v1.1.0 | *自我进化引擎 Agent、RL 升级、置信度过滤、多层记忆隔离。* |
| v1.0.10 | *Hermes v0.14.0 完整适配。* |
| v1.0.9 | *OpenClaw / OpenCode / Claude Code 三平台兼容修复。* |
| v1.0.8 | *平台感知记忆、Hermes 适配插件、WAL 并发模式。*

📖 *必看* 完整更新日志：[CHANGELOG.zh-CN.md](docs/CHANGELOG.zh-CN.md)


---
## 🔗 快速链接

| 文档 | 说明 |
|:---------|:-----------|
| [安装指南](docs/INSTALL.zh-CN.md) | 环境要求、一键安装、Hermes 设置、Python 快速上手 |
| [API 参考](docs/API.zh-CN.md) | 全部 20+ HTTP 端点 |

数据存储在 ~/.echomind/memory.db（SQLite 单文件），备份直接复制即可。



## 🔭 愿景

AI 不是工具，是协作者。协作者不应该每次见面都"重新认识你"。

EchoMind Memory Engine 让你的 AI：

- 记得你的风格、偏好和习惯
- 记得你修复过的 bug 和尝试过的方法
- 记得你研究过的论文和理论模型
- 拥有强化学习与反思推理的智能系统，每次交互后越用越聪明
- 这不是一个插件，这是具有*自我反思记忆*的*AI 多智能体记忆神经网络*。


## 📫 联系方式
*email：*[jasonyouatgmaildotcom](mailto:jasonyouatgmaildotcom)

---

## ❓ Q&A *点击展开*

<details>
<summary><b>Hermes Agent分身隔离及常见问题</b></summary>

### Q: 如何在 Hermes 分身（Profile）中使用 EchoMind？

EchoMind v1.1.6+ 支持 Hermes Profile 级别的记忆隔离。

**安装一次即可**：
```bash
./install.sh
```

**自动行为**：
- 默认分身 → 记忆存储在 `profile='default'`
- 其他分身（如 weixin）→ 自动创建符号链接，记忆存储在 `profile='weixin'`
- 两个分身的记忆在同一 `~/.echomind/memory.db` 中，互不干扰
- 历史数据自动归入 `default` profile

**同一分身内按项目隔离**：
```yaml
# hermes config.yaml
memory:
  provider: echomind
  project: echomind  # 可选，同一分身内按项目过滤
```

**手动为新分身建立链接**（如果创建分身在安装之后）：
```bash
ln -s ~/.hermes/plugins/echomind ~/.hermes/profiles/微信分身名/plugins/echomind
```

---

### Q: EchoMind 是否支持 Windows？

支持。v1.1.6+ 已修复跨平台路径解析，Windows 路径（如 `C:\Users\...\profiles\weixin\...`）可正确提取 profile 名称。
如果使用 WSL，路径格式与 Linux 一致。

---

### Q: 多个分身同时使用 EchoMind 会冲突吗？

不会。v1.1.6+ 采用以下机制保障并发安全：
1. **WAL 模式**：SQLite 写前日志，支持多进程并发读
2. **busy_timeout=5000**：遇到锁等待 5 秒
3. **自动重试**：极端情况下指数退避重试 3 次

---

### Q: 如何降级到旧版本？

> ⚠️ **重要**：降级时旧版 SELECT 无 `WHERE profile = ?` 过滤，所有分身数据对默认分身可见。

**安全降级步骤**：
1. 备份 `~/.echomind/memory.db`
2. 清除非 default 数据：
   ```sql
   DELETE FROM task_memory WHERE profile != 'default';
   DELETE FROM user_memory WHERE profile != 'default';
   ```
3. 再回退旧版

**推荐**：保留新版，不做降级。

---

### Q: 数据存储在哪里？如何备份？

所有数据存储在单文件 `~/.echomind/memory.db` 中。备份只需复制该文件：
```bash
cp ~/.echomind/memory.db ~/.echomind/memory.db.backup-$(date +%Y%m%d)
```

---

### Q: 迁移后数据会丢失吗？

不会。SQLite `ALTER TABLE ADD COLUMN ... DEFAULT 'default'` 是 O(1) 元数据操作，不逐行修改数据，存量 37MB 数据完整保留，自动归入 `default` profile。

---

### Q: EchoMind 是否兼容 Hermes v0.16.0？

是。EchoMind v1.1.6+ 已适配 Hermes v0.16.0 新增的 `on_session_switch(rewound=True)` 参数。
当用户执行 `/undo N` 截断对话历史时，EchoMind 自动清空上下文缓存，避免记忆污染。

### Q: EchoMind 是否兼容 Hermes v0.17.0？

是。EchoMind v1.2.0+ 完整支持 Hermes v0.17.0 的 MemoryProvider 接口，包括 `get_config_schema()`、`backup_paths()`、`save_config()` 方法。
兼容范围：Hermes v0.13.0 – v0.17.0。

</details>

<details>
<summary><b>🌐 MCP 网关设置与常见问题</b></summary>

### Q: 如何将 EchoMind 通过 MCP 连接到 Claude Code？

**本地 stdio 模式**（无需 HTTP 服务）：
```bash
claude mcp add echomind -- python ~/.hermes/skills/echomind-memory/adapters/mcp_gateway.py
```

**远程 HTTP 模式**（需要 `python main.py` 在 8005 端口运行）：
```json
{
  "mcpServers": {
    "echomind": {
      "url": "http://<你的服务器>:8005/mcp",
      "type": "streamableHttp"
    }
  }
}
```

> ⚠️ HTTP MCP 模式需要 EchoMind HTTP 服务保持运行（`python main.py`）。如果服务停止，远程 MCP 连接将不可用。stdio 模式不受影响。

### Q: MCP 有哪些可用工具？

EchoMind 提供 7 个 MCP 工具：

| 工具 | 说明 |
|------|------|
| `echomind_retrieve` | 按查询搜索长期记忆 |
| `echomind_store` | 将交互结果持久化到记忆 |
| `echomind_search` | 搜索会话转录 |
| `echomind_feedback` | 对检索结果提供反馈 |
| `echomind_reflect` | 触发最近记忆的反思 |
| `echomind_delete` | 删除特定记忆条目 |
| `echomind_health` | 检查服务健康状态 |

### Q: MCP 连接失败怎么办？

1. **stdio 模式**: 检查网关路径是否正确 — `python -c "from adapters.mcp_common import handle_mcp_request"` 应正常运行
2. **HTTP 模式**: 确认 `python main.py` 正在运行，`curl http://127.0.0.1:8005/health` 返回 `"status":"ok"`
3. **认证**: 如果 `echomind_config.yaml` 中配置了 `api_key`，需要设置 `ECHOMIND_API_KEY` 环境变量

### Q: MCP 是否支持 Claude Code 以外的工具？

是。MCP stdio 兼容任何 MCP 客户端（Claude Desktop、Cursor、Cline 等）。远程 HTTP MCP 使用 Streamable HTTP 传输协议，这是 MCP 社区标准协议。

</details>
