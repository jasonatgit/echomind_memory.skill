# 为 EchoMind 新增"管理科学与工程"研究领域记忆能力

## 概述

本文档完整记录了如何在 EchoMind 记忆系统中增加一个新的记忆维度——**研究记忆（Research Memory）**，专门用于存储和检索"管理科学与工程"领域的论文、理论、模型、方法等结构化知识。

---

## 架构设计

### 新增的记忆层级

```
EchoMind Memory System
├── Context Memory    (对话上下文)
├── Task Memory       (任务状态)
├── User Memory       (用户偏好/习惯)
├── Knowledge Memory  (通用知识)
├── Experience Memory (经验总结)
└── Research Memory   ←  新增：管理科学与工程研究记忆
    ├── ResearchPaper  (论文/文献)
    └── ResearchNote   (研究笔记)
```

### 数据流

```
用户提问
  │
  ▼
_extract_task_features()
  ├── 检测是否包含研究领域关键词
  └── 识别细分领域 (research_domain)
        │
        ▼
retrieve_for_task()
  ├── 若 requires_research == True
  └── 调用 research_agent.search_papers(query, domain)
        │
        ▼
_compute_importance()
  └── 按 relevance × importance_score 加权排序
        │
        ▼
返回 working_memory（含 research 来源）
```

---

## 修改的文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `models/research.py` | **新增** | 研究记忆数据模型 |
| `memory_agent.py` | **修改** | 新增 ResearchMemoryAgent + 集成到 MainMemoryAgent |
| `storage/postgres.py` | **修改** | 新增 research_papers/research_notes 表 CRUD |
| `storage/schema.sql` | **修改** | 新增 DDL 和索引 |
| `skill.yaml` | **修改** | source 枚举值增加 research |

---

## 各文件改动详情

### 1. `models/research.py` — 数据模型

```
ResearchPaper
├── id              : str      (UUID)
├── title           : str      (论文标题)
├── authors         : List[str] (作者列表)
├── year            : int?     (发表年份)
├── journal         : str?     (期刊/会议)
├── abstract        : str      (摘要)
├── keywords        : List[str] (关键词)
├── domain          : str      (细分领域，见下方)
├── paper_type      : str      (theory/method/application/review)
├── key_points      : List[str] (核心知识点，供检索用)
├── importance_score: float    (重要性评分 0~1)
├── metadata        : dict     (扩展元数据)
└── created_at      : datetime

ResearchNote
├── id              : str      (UUID)
├── user_id         : str
├── topic           : str      (笔记主题)
├── content         : str      (笔记内容)
├── linked_papers   : List[str] (关联论文ID)
├── tags            : List[str]
├── created_at      : datetime
└── updated_at      : datetime
```

### 2. `memory_agent.py` — 核心逻辑

**新增类 `ResearchMemoryAgent`：**

- `add_paper(paper)` — 存储一篇论文
- `search_papers(query, domain, top_k)` — 按标题/关键词/摘要多字段匹配检索
- `add_note(note)` — 存储研究笔记
- `search_notes(query, tags, top_k)` — 检索研究笔记
- `get_domain_overview(domain)` — 按细分领域汇总知识概览

**集成到 `MainMemoryAgent`：**

| 改动点 | 位置 | 说明 |
|--------|------|------|
| `self.research_agent` | `__init__` | 初始化 ResearchMemoryAgent |
| `_extract_task_features()` | 新增 `requires_research` / `research_domain` 字段 | 检测是否涉及研究领域，识别细分方向 |
| `retrieve_for_task()` | 新增 research 检索分支 | 当 `requires_research=True` 时并发检索论文 |
| `_compute_importance()` | 新增 `research` 评分逻辑 | 按 `relevance × weight + importance_score × 0.3` 计算 |
| `_detect_research_domain()` | 新增私有方法 | 按关键词映射到 10 个细分领域 |
| `sync_to_code_project()` | 新增论文摘要同步 | 将 top-3 论文写入 .echomind/ |

### 3. `storage/postgres.py` — 持久化

**`ensure_tables()` 新增两张表：**

- `research_papers` — 论文数据
- `research_notes` — 研究笔记

**新增 CRUD 方法：**

- `save_research_paper(...)` — 写入/更新论文
- `save_research_note(...)` — 写入/更新笔记
- `get_research_papers(domain, limit)` — 按领域查询论文

### 4. `storage/schema.sql` — DDL

```sql
CREATE TABLE research_papers (
    id VARCHAR(64) PRIMARY KEY,
    title TEXT NOT NULL,
    authors JSONB DEFAULT '[]',
    year INTEGER,
    journal TEXT,
    abstract TEXT DEFAULT '',
    keywords JSONB DEFAULT '[]',
    domain VARCHAR(64) DEFAULT 'general',
    paper_type VARCHAR(32) DEFAULT 'theory',
    key_points JSONB DEFAULT '[]',
    importance_score FLOAT DEFAULT 0.5,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE research_notes (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(128),
    topic TEXT NOT NULL,
    content TEXT DEFAULT '',
    linked_papers JSONB DEFAULT '[]',
    tags JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 5. `skill.yaml` — source 枚举

`source` 字段增加 `research` 枚举值。

---

## 支持的管理科学与工程细分领域

| 领域标识 | 中文名 | 触发关键词 |
|----------|--------|-----------|
| `operations_research` | 运筹学 | 运筹学, 线性规划, 整数规划, operations research |
| `supply_chain` | 供应链 | 供应链, 库存, 物流, supply chain |
| `decision_analysis` | 决策分析 | 决策分析, 多准则, AHP, decision analysis |
| `optimization` | 最优化 | 优化, 最优, 梯度, optimization |
| `simulation` | 仿真模拟 | 仿真, 模拟, 蒙特卡洛, simulation |
| `game_theory` | 博弈论 | 博弈论, 纳什均衡, game theory |
| `forecasting` | 预测 | 预测, 时间序列, forecasting |
| `project_management` | 项目管理 | 项目管理, 关键路径, project management |
| `queuing_theory` | 排队论 | 排队论, 队列, queuing |
| `general` | 通用 | 其他 |

---

## 使用示例

```python
from models.research import ResearchPaper

# 1. 存储一篇论文
await memory_agent.research_agent.add_paper(ResearchPaper(
    title="Supply Chain Coordination with Contracts",
    authors=["Tsay", "Nahmias", "Agrawal"],
    year=1999,
    journal="Production and Operations Management",
    domain="supply_chain",
    paper_type="review",
    keywords=["supply chain", "coordination", "contract"],
    key_points=[
        "Contracts can align incentives in decentralized supply chains",
        "Revenue sharing, buyback, quantity flexibility are common contract types",
    ],
    importance_score=0.85,
))

# 2. 自动检索研究记忆（via retrieve_memory）
result = await memory_agent.retrieve_for_task(
    "供应链协调合同机制综述",
    user_id="researcher_001"
)
# result["working_memory"] 中将包含 source="research" 的记录

# 3. 存储一篇研究笔记
from models.research import ResearchNote
await memory_agent.research_agent.add_note(ResearchNote(
    user_id="researcher_001",
    topic="供应链契约分类笔记",
    content="收入共享契约适用于...",
    tags=["supply_chain", "contract"],
))
```

---

## 扩展新的研究领域

若要增加新的细分领域（如"计算社会科学"），只需：

1. **`memory_agent.py` 中 `_detect_research_domain()`** 增加映射：
   ```python
   "computational_social_science": ["计算社会", "社会网络", "computational social"],
   ```
2. **`ResearchMemoryAgent.__init__` 中 `ms_domains`** 增加名称
3. 后续存储论文时将 `domain` 设为新值即可

所有检索、评分、持久化逻辑自动适配。