# EchoMind 更新日志

## v1.2.10 — 算法优化轮 (2026-08-15)

算法优化轮：补齐 OSS 反思闭环，并强化 RL 学习路径的按用户隔离。

| 领域 | 改动 |
|------|------|
| **反思闭环 (OSS)** | `_reflective_fallback.py` 实现 4 个 `_merge_*`/`_save_reflection` 桩并消费 `_process_reflection` 产物 (P1-A)；Pro `.pyx` 新增与 `decay_all` 对称的正向 `_reinforce_weights` 臂，并修复 few-shot 提示词构建 bug (P1-B) |
| **RL 信用分配** | `_update_weights` 只对 mapped 源真实出现的维度给予方向性增量 (P2-B)——此前 softmax + M-4 中性回退会稀释每次正向反馈，任何维度份额都无法有效抬升 |
| **归一化不变量** | 声明 `_WEIGHT_INVARIANT_UPDATE/DECAY = "linear"` 并把周期性反发散 `decay_all` 接入 `_update_weights` (P3-A)；修复 `decay_all` 先归一化后 clamp 的顺序（range 不变量） |
| **日限额 per-user + 持久化** | 反思日限改为按 `(user_id, 日期)` 计并持久化到 SQLite（`reflection_daily_count`），重启后仍生效 (P5-B) |
| **RL meta-state per-user** | LR/探索调度、history、发散快照、累计计数全部按用户键控——一个用户的反馈不再推进另一个用户的学习轨迹 (P5-A) |
| **存储索引** | 补幂等连接/查找索引（knowledge 内容、task/experience 按 user+created、reflections 按 user+created）(P6-A) |

**测试：** 80 通过（含新增日限、meta-state 隔离、反思闭环回归测试）；2 个既有收集错误不在范围内。

---
## v1.2.9 — Markdown 呈现与 Hermes v0.20 适配 (2026-08-12)

| 功能 | 说明 |
|------|------|
| **Markdown 记忆档案导出** | `export_memory_to_markdown()` 生成完整 .md（9 章），`core/markdown_renderer.py` 零新依赖 |
| **注入层紧凑 Markdown** | `_format_prefetch_context` 改为 `<memory-context>` 块（Hermes v0.20 兼容） |
| **Hermes v0.20 适配** | 根 `__init__.py` 的 `register(ctx)` + `plugin.yaml` `kind: exclusive` |
| **Cognitive Position 实现** | cognitive_pos (nok/fok/exo) 完整生命周期 |
| **HTTP 端点** | `GET /api/memory/archive` |
| **Bug 修复** | register 位置 (BUG-1), 无效测试 (BUG-2), search_all 死代码 (BUG-3) |

**测试:** 62 项通过。

---
## v1.2.8 — 自我反思吸收 Phase 1+2 (2026-08-11)

| 功能 | 说明 |
|------|------|
| **认知模式（Epistemic Mode）** | 知识条目现在在 metadata 中携带 `epistemic_mode`（user_provided / reasoned / fuzzy / referenced），写入时按来源自动判定——零 LLM 成本 |
| **溯源列** | 迁移 v9 为 `knowledge_evolution` 添加 `origin_agent`、`origin_session_id`、`origin_turn` 三列，实现记忆供应链追踪 |
| **自我反思评分** | `compute_autoreflection_score()` 评估四标准成熟度：情境觉察、架构一致性、从架构分析、整合与扩展——返回 (分数 0-4, 诊断摘要) |
| **系统提示诊断** | `system_prompt_block()` 现在向智能体上下文追加实时记忆健康信息（统计、RL 权重、演化状态） |
| **知识搜索** | 搜索结果包含 `epistemic_mode` 和 `epistemic_detail`，供下游信任评估使用 |
| **认知位置** | 知识条目在 metadata 中追踪 `cognitive_pos`（nok/fok/exo）——上下文邻近度，补充 Ebbinghaus 遗忘曲线 |

**测试:** 新增 8 项回归测试（认知解析器、溯源迁移列、自我反思评分、知识搜索）；全量 56 项通过。

---
## v1.2.7 — 深度代码审查修复 & 回归测试 (2026-08-04)

**审查方法:** full deepseek-v4-flash 代码审查 + 4 路并行记忆数据链路审计，修复后 + 48 项测试套件（33 原有 + 15 新）。

| 领域 | 修复 |
|------|------|
| **数据链路/新鲜度** | `_load_from_db` 恢复所有时间戳（Ebbinghaus 在重启后保持）；统一 `last_access_at` 格式；knowledge `last_access_at` 贯通；user `model_dump(mode=json)`；`_freshness` 处理 datetime 对象 |
| **事务** | `_batch_active` + `_maybe_commit()` 门控 → `transaction()` 现在真正原子化（失败时回滚） |
| **持久化** | 补全 task/experience/knowledge/paper/note 的 UPSERT `DO UPDATE SET` 字段；迁移 v3 保留 `created_at` |
| **调度/API** | `main.py` 转发 `project`/`session_id`/`title`/`correction`；`api_delete_user` → HTTP 500；`mcp_gateway` 薄封装（版本 1.2.7）；reflect profile 作用域 |
| **RL/安全** | 日限额跨 UTC 天重置；状态写入加 `db._lock`；单次 freshness；`_content_index` 在加载时重建；安全 JSON 加载；transcript upsert；`batch_score` 解析 |
| **关键 bug** | `models/context.py` 缺少 `Optional` 导入（已修复） |

**测试:** 修复 conftest + storage/core 断言；新增 `tests/test_regressions.py`（15 tests）。

---
## v1.2.3  新增功能

**核心要点：**
*RL advantage baseline、RCW 源权重分配、知识多样性、profile 导出。*

| 功能 | 说明 |
|------|------|
| **RL Advantage Baseline** | 线性就近加权历史基线替代裸 reward — 更稳定的权重更新 |
| **RCW 源权重分配** | relevance × trust 分数映射到权重维度 — 更公平的源贡献分配 |
| **KPop 感知衰减** | 策略快照偏离时触发额外的 KL 散度敏感衰减 |
| **知识多样性** | 领域感知 top-K 检索确保结果覆盖多个知识领域 |
| **Profile 导出** | 人类可读的 profile.md 包含偏好、知识、经验、论文、热点领域 |
| **热点领域追踪** | 标签和领域统计在 behavior hints 中暴露供 agent 感知 |


---
## v1.2.2  新增功能

**核心要点：**
*记忆生命周期管理、知识演化追踪、实体抽取、Streamable HTTP MCP。*

| 功能 | 说明 |
|------|------|
| **记忆状态机** | Active → Stale → Archived → Superseded 生命周期追踪，基于 Ebbinghaus 新鲜度自动状态转换 |
| **知识演化追踪** | Jaccard + LLM 混合检测（取代/丰富/确认/挑战四种关系） |
| **记忆健康报告** | 输出中增加记忆健康提示节 |
| **Flags 标记系统** | 自动检测 needs_verification 和 contradiction 的知识条目 |
| **实体抽取** | LLM 优先 + 关键词兜底（技术/概念实体） |
| **Streamable HTTP MCP** | `POST /mcp` + `GET /mcp` — EchoMind MCP 支持通过 JSON-RPC over HTTP 远程访问 |
| **共享 MCP 工具层** | stdio 和 HTTP 双传输共享单一工具定义 |


---
## v1.2.0  新增功能

**核心要点：**
*MCP stdio 网关、艾宾浩斯遗忘曲线、会话隔离上下文管理、记忆 CRUD。*

| 功能 | 说明 |
|------|------|
| **MCP stdio 网关** | 7 个原生 Claude Code 工具（retrieve/store/search/feedback/reflect/delete/health），通过 stdio JSON-RPC 协议 |
| **Ebbinghaus遗忘曲线** | 基于新鲜度的记忆评分 ，覆盖全部6种记忆类型，自动排除冷数据 |
| **记忆删除 API** | 支持单条删除、用户数据全清、TTL 过期清理的 REST 端点 |
| **会话隔离上下文管理** | 每个 session_id 独立上下文窗口，LRU 淘汰 |
| **会话消息归档** | 淘汰的会话消息自动保存到数据表 |
| **用户纠正信号检测** | 中英文关键词匹配纠正信号，触发即时反思 |
| **6 类偏好推理** | code_style, response_style, platform, language, depth, tone — 关键词驱动，配置化 |
| **自适应反思批处理** | 基于周活跃度动态调整 |
| **RL 余弦衰减 + Epsilon-Greedy** | 余弦学习率衰减防止后期震荡；epsilon-greedy 探索跳出局部最优 |
| **SQLite Schema 迁移系统** | 结构化迁移列表，支持事务回滚 |
| **原子化批量写入** | 将 5 次保存操作包裹在单个事务中 |
| **Hermes Agent v0.17.0 适配** | 完整实现 `get_config_schema()`、`backup_paths()`、`save_config()` 等新接口 |


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

##  各版本学术参考

本次发行的 v1.1.0 的技术方案中Self-Reflective Agent部分设计受到以下研究的启发：

### 1、SAGE: Self-evolving Agents with Reflective and Memory-Augmented Abilities

Liang, X., He, Y., Xia, Y., Song, X., Wang, J., Tao, M., Sun, L., Yuan, X., Su, J., Li, K., Chen, J., Yang, J., Chen, S., & Shi, T. (2024).

- **论文地址：** [arXiv:2409.00872](https://arxiv.org/abs/2409.00872)
- **发表期刊：** *Neurocomputing* (2025)
- **使用版本:** Echomind Memory Engine v1.1.0


### 2、SRMA: Self-Reflective Memory Consolidation in Agentic Architectures

Satya, P. R. B. (2026).

- **论文地址：** [IJCA Vol.187 No.73](https://www.ijcaonline.org/archives/volume187/number73/self-reflective-memory-consolidation-in-agentic-architectures/)
- **发表期刊：** *International Journal of Computer Applications*, 187(73)
- **使用版本:** Echomind Memory Engine v1.1.0


### 3、Lewis (2026) "Autoreflection: How Agentic Strange Loops Turn Human Culture into AI Infrastructure" 
- **论文地址：** https://arxiv.org/abs/2608.03800
- **使用版本:** Echomind Memory Engine v1.2.8
- **引用范围:** 知识认知状态分类、溯源追踪、架构自诊断、自我反思评分


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
