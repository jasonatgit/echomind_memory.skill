# EchoMind Markdown 呈现：让 AI 记忆从"黑盒"变为"可读文档"

> 一项轻量、零依赖的能力，将 EchoMind 的 6 类记忆系统转化为一份完整的、可分节、可导航的 Markdown 档案。
>
> 作者：EchoMind 团队
> 日期：2026 年 8 月

---

## 一、为什么要呈现记忆数据

EchoMind 储存了你的 AI 智能体所有的记忆——用户的代码风格偏好、调试过的 bug、研究过的论文、反思提取的知识。但是这些数据一直以结构化形式存在于 SQLite 数据库中。对用户而言，它们是不可见的"黑盒"。

这带来了三个问题：

1. **用户无法直观理解"AI 记住了什么"**——你需要手动查看 `~/.echomind/memory.db` 中的表才能看到内容。
2. **无法区分记忆的可信度**——一条用户亲口告知的事实，和一条 LLM 生成的推测，两者在数据库中看起来是一样的。
3. **Agent 自己也需要了解"我是谁"**——autoreflection 论文的核心洞察是：Agent 的"自我"是一组可编辑文件的当前状态。如果这些文件不是 markdown，Agent 就无法在激活时高效"读回"自己的状态。

v1.2.9 引入的 Markdown 呈现能力正是为了解决这三个问题：**将记忆从数据库黑盒转化为一份完整的、人机同读的 Markdown 文档**。

---

## 二、EchoMind 用 Markdown 呈现了哪些数据

`export_memory_to_markdown()` 一次调用生成一份完整的 `memory.md`，共 9 个章节：

| 章节 | 内容 | 亮点 |
|------|------|------|
| **🧠 记忆健康总览** | 版本号 + 自我反思评分 + 6 类记忆（活跃/陈旧/归档）统计表 | 一眼掌握记忆系统的健康状态 |
| **👤 用户画像** | 6 类偏好（代码风格/回复风格/语言/深度/语气）+ 习惯 + 最近活动轨迹 | 来自 `preferences` + `habits` + `history` |
| **📚 知识库** | 按认知状态分区：✅ 用户确认 / 🧠 推理产物 / ⚠️ 待验证 / 📎 外部引用 —— 每一条知识显示可信度、认知位置 (⚡ nok/🔽 fok/📖 exo)、所属领域 | 这是 Markdown 呈现的核心亮点——epistemic 分类直接可视化 |
| **💡 经验库** | ✅ 成功经验 / ❌ 失败经验 —— 显示摘要和频率 | 你踩过的坑和你成功过的模式 |
| **🗂️ 任务进度** | 🚧 进行中 / ✅ 已完成 —— 勾选列表 | 来自 `task_memory` |
| **💬 上下文规模** | 活跃/陈旧/归档的会话数量 | 内存占用一览 |
| **📄 研究文献** | 论文标题、领域、年份表 | 来自 `research_papers` |
| **🪞 反思洞察** | 最近一次反思的关键洞察 + 新知识提取 | 来自 `reflections` 表 |
| **🔍 自我反思评分** | 四标准成熟度模型（C1-C4）+ 诊断建议 | 来自 `compute_autoreflection_score()` |

注入层（Agent 上下文）使用紧凑版本：一句话用户画像 + 最多 5 条最相关记忆（含可信度标签），包裹在 `<memory-context>` 标记块中，与 Hermes v0.20 的 `build_memory_context_block` 兼容。

---

## 三、呈现能力给记忆引擎赋能了哪些能力

1. **可解释性与审计**：任何时候运行 `sync_to_code_project()`，你的项目 `.echomind/` 目录下就有一份完整的 `memory.md`——不需要手动查数据库。
2. **幻觉检测**：`⚠️ 待验证 (fuzzy)` 区块集中展示了所有 LLM 生成但未经验证的知识，帮助用户发现潜在的幻觉。
3. **自动诊断**：`🔍 自我反思评分` 显示记忆系统当前的成熟度——从 0（纯遥测）到 4（真正的自我反思），并给出具体建议。
4. **溯源追踪**：每一条知识旁标注了认知状态（user_provided / reasoned / fuzzy / referenced），你可以追查"这条知识从哪来、可信度多少"。
5. **人机同读**：同一套数据既以 9 节完整档案给人看，也以紧凑 `<memory-context>` 块喂给 LLM——Agent 和用户基于同一份记忆事实沟通。

---

## 四、本次呈现能力大开发涉及的技术能力

| 技术点 | 说明 |
|--------|------|
| **纯 Python f-string 渲染** | `core/markdown_renderer.py` —— 零新依赖，10 个 `render_*()` 独立函数，所有输出一目了然 |
| **Query/Render 分离** | `memory_agent.py` 负责数据提取（`_query_archive_data()`）→ 传入轻量 dataclass (`MemoryArchive`) → 渲染器只负责格式化，两者各自独立、独立可测 |
| **轻量 dataclass 数据模型** | `KnowledgeRow` / `ExperienceRow` / `TaskRow` / `MemoryArchive` —— 无 DB 依赖，任何 Agent 框架准备好数据即可调用渲染器 |
| **多文件拼接为用户无感知** | 9 个独立渲染函数各自生成 markdown 片段 → `render_full_archive()` 一次性拼接为完整的 `.echomind/memory.md` |
| **cognitive_pos 完整实现** | Moltspeak 的 nok/fok/exo 三层认知位置，在每条知识上标记"它当前处在 agent 认知空间的哪个位置" |
| **Hermes v0.20 兼容** | `<memory-context>` 紧凑块 + `register(ctx)` 顶层 re-export + `plugin.yaml` 的 `kind: exclusive` —— 适配 Hermes 最新的插件加载机制 |
| **HTTP 端点暴露** | `GET /api/memory/archive` —— 随时随地通过 API 获取完整档案 |

---

## 五、EchoMind 完整 Markdown 呈现示例

以下是一个经过简化的 `.echomind/memory.md` 示例：

```markdown
# 🧠 EchoMind Memory Archive

> EchoMind v1.2.9 | Generated 2026-08-12T14:30:22+00:00
> **Self-Reflection Score: 3/4**

## 📊 Memory Health

| Type | Active | Stale | Archived |
|------|--------|-------|----------|
| knowledge | 20 | 8 | 7 |
| experience | 30 | 5 | 4 |
| task | 30 | 5 | 8 |
| context | 25 | 10 | 8 |
| user | 2 | 0 | 0 |
| paper | 5 | 0 | 1 |

## 👤 User Profile

### Preferences
| Dimension | Value |
|-----------|-------|
| response_style | concise |
| code_style | pep8 |
| language | zh |

### Habits
- active_time: morning
- frequent_language: python

## 📚 Knowledge

### ✅ User Confirmed (2)
| Knowledge | Trust | Cognitive Pos | Domain |
|-----------|------:|:---:|--------|
| PostgreSQL 主键自动创建索引 | 0.95 | ⚡ nok | echomind |
| WSL 代理阻断 GitHub HTTPS 需 unset | 0.90 | 📖 exo | general |

### 🧠 Reasoned (3)
| Knowledge | Trust | Cognitive Pos | Domain |
|-----------|------:|:---:|--------|
| HNSW 索引在 100K+ 规模优于 IVFFlat | 0.70 | 📖 exo | echomind |

### ⚠️ Unverified (2)
| Knowledge | Trust | Cognitive Pos | Domain |
|-----------|------:|:---:|--------|
| pgvector HNSW 优于 IVFFlat at scale | 0.60 | 📖 exo | echomind |

## 💡 Experience

### ✅ Success (5)
| Summary | Freq |
|---------|-----:|
| EchoMind 升级流程 | 2 |

## 🔍 Self-Reflection Score

**3/4**

  ✅ C1: situated awareness — persistence active, reflection configured
  ✅ C2: architectural congruence — 20 active knowledge records
  ✅ C3: analysis-from-architecture — LLM endpoint configured
  ❌ C4: incorporation-and-expansion — 尚无跨会话自我调优记录
```

---

## 六、其他你应该知道的内容

### 零新依赖、轻量
整个 Markdown 渲染模块（`core/markdown_renderer.py`）只有约 190 行纯 Python 代码——没有 Jinja2、没有 Pandas、没有任何第三方依赖。它可以在任何运行 Python 3.10+ 的环境中工作。

### 向后兼容 + 多版本 Hermes
- Hermes v0.13-v0.17（duck-typing 路径）✅
- Hermes v0.20+（新 `register()` 入口）✅
- 现有 `sync_to_code_project()` 自动生成 `memory.md`，无需额外配置

### 如何获得你的记忆档案
| 方式 | 命令/端点 |
|------|---------|
| **自动导出** | `sync_to_code_project()` → 自动生成 `.echomind/memory.md` |
| **HTTP API** | `GET /api/memory/archive` |
| **Python API** | `memory_agent.export_memory_to_markdown("your_user_id")` |

---

**参考文献：**
- EchoMind v1.2.9 更新日志（2026）。详见 `docs/CHANGELOG.md`。