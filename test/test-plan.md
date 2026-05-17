# EchoMind Memory — 测试方案与测试用例

> 版本: v1.1.0 | 最后更新: 2026-05-15
>
> **测试原则:**
> - 新增功能必须追加对应测试方案和用例
> - 每个功能模块至少覆盖: 正常路径、边界条件、异常路径
> - 不参与 GitHub 发布（本地测试文档）

---

## 目录

1. [测试环境](#1-测试环境)
2. [核心引擎测试](#2-核心引擎测试)
3. [存储层测试](#3-存储层测试)
4. [Self-Reflective Agent 测试 (v1.1.0)](#4-self-reflective-agent-测试-v110)
5. [适配器测试](#5-适配器测试)
6. [HTTP API 测试](#6-http-api-测试)
7. [平台集成测试](#7-平台集成测试)
8. [回归测试清单](#8-回归测试清单)

---

## 1. 测试环境

| 项目 | 值 |
|------|-----|
| Python | 3.10+ |
| 存储 | SQLite WAL |
| 数据库 | ~/.echomind/memory.db |
| 服务端口 | 8005 |
| 测试目录 | `test/` |

### 快速启动

```bash
cd /mnt/d/llm/echomind_memory.skill
python3 -c "from core.memory_agent import MainMemoryAgent; agent = MainMemoryAgent(); agent.enable_persistence(); print('OK')"
```

---

## 2. 核心引擎测试

### 2.1 MainMemoryAgent 初始化

| 编号 | 用例 | 步骤 | 预期 |
|------|------|------|------|
| CORE-001 | 默认初始化 | `agent = MainMemoryAgent()` | 6 个 Agent 就绪，persistence=false |
| CORE-002 | 开启持久化 | `agent.enable_persistence()` | SQLite 连接，8 表创建，`_persistence_enabled=True` |
| CORE-003 | 持久化状态切换 | enable → disable → enable | 状态正确切换，无残留 |
| CORE-004 | ReflectiveAgent 集成 | `agent = MainMemoryAgent()` | `agent.reflective` 存在，`agent._store_count=0` |

### 2.2 Memory Store

| 编号 | 用例 | 步骤 | 预期 |
|------|------|------|------|
| CORE-101 | 基本 store | `agent.store(user_id, task_id, context, ...)` | 返回 dict，含 task_id |
| CORE-102 | platform-aware store | store(platform="hermes") | context 表 platform="hermes" |
| CORE-103 | store 触发计数 | 连续 store 8 次 | `_store_count=8`, `_pending_reflection=True` |
| CORE-104 | store 无持久化时 | agent.disable_persistence(); store() | 仅内存，不写 SQLite |
| CORE-105 | 空 context store | store(context=[]) | 正常处理，不崩溃 |

### 2.3 Memory Retrieve

| 编号 | 用例 | 步骤 | 预期 |
|------|------|------|------|
| CORE-201 | 基本检索 | `agent.retrieve_for_task(task_context)` | 返回 retrieved_memories 列表 |
| CORE-202 | platform 过滤 | retrieve(platform="hermes") user has hermes+openclaw memories | hermes 的权重更高 |
| CORE-203 | 空数据库检索 | 新用户检索 | 返回空列表，不报错 |
| CORE-204 | task_context=None | retrieve(task_context=None) | 返回空列表 |

### 2.4 RL 反馈

| 编号 | 用例 | 步骤 | 预期 |
|------|------|------|------|
| CORE-301 | 正向反馈 | `agent.record_feedback(feedback="positive")` | 记忆权重提升 |
| CORE-302 | 负向反馈 | `agent.record_feedback(feedback="negative")` | 记忆权重降低 |
| CORE-303 | RL 权重持久化 | feedback → disable → enable | 权重从 SQLite 恢复 |
| CORE-304 | 无检索记忆时反馈 | feedback with empty retrieved_memories | 不崩溃 |

### 2.5 记忆类型专项

| 编号 | 用例 | 步骤 | 预期 |
|------|------|------|------|
| CORE-401 | user_memory 写入 | store → 检查 user_memory 表 | preferences 更新 |
| CORE-402 | task_memory 写入 | store with task_status | task 表有记录 |
| CORE-403 | context_memory 写入 | store with messages | context 表有记录，platform 正确 |
| CORE-404 | experience_memory 写入 | store with success=True | experience 表有记录 |
| CORE-405 | knowledge_memory 写入 | 涉及已知领域的对话 | knowledge 表有记录 |
| CORE-406 | research_papers 写入 | `add_research_paper(...)` | paper 表有记录 |
| CORE-407 | research_notes 写入 | `add_research_note(...)` | note 表有记录 |

---

## 3. 存储层测试

### 3.1 SqliteStore 初始化

| 编号 | 用例 | 步骤 | 预期 |
|------|------|------|------|
| DB-001 | 首次连接 | `SqliteStore().connect(db_path)` | 8 张表创建（含 reflections） |
| DB-002 | 重复连接 | 已存在 DB 再 connect | 幂等，不丢数据 |
| DB-003 | WAL 模式验证 | connect → 检查 journal_mode | `PRAGMA journal_mode=wal` |
| DB-004 | 路径不存在 | `connect("/nonexistent/dir/memory.db")` | 自动创建目录 |

### 3.2 reflections 表 (v1.1.0)

| 编号 | 用例 | 步骤 | 预期 |
|------|------|------|------|
| DB-101 | 表结构 | connect → 检查 reflections 表 | 13 列，id 为主键 |
| DB-102 | 写入反思 | `save_reflection(data)` | JSON 字段正确序列化 |
| DB-103 | 读取反思 | 写入→读取 | `get_recent_episodic` 返回正确条数 |
| DB-104 | 空表读取 | 新DB `get_recent_episodic` | 返回空列表 |
| DB-105 | 旧版迁移 | v1.0.8 DB → v1.1.0 connect | 其他表完整，reflections 新增 |

### 3.3 并发测试

| 编号 | 用例 | 步骤 | 预期 |
|------|------|------|------|
| DB-201 | 多线程读取 | 2 线程同时检索 | 无死锁 |
| DB-202 | 读写交错 | 线程A写 + 线程B读 | WAL 模式无阻塞 |

---

## 4. Self-Reflective Agent 测试 (v1.1.0)

### 4.1 ReflectionOutput 模型

| 编号 | 用例 | 步骤 | 预期 |
|------|------|------|------|
| REF-001 | 最小有效输出 | `ReflectionOutput(key_insights=["test"], confidence=0.8)` | 创建成功 |
| REF-002 | 完整输出 | 8 字段全部填充 | 创建成功 |
| REF-003 | 非法置信度(>1.0) | confidence=1.5 | 验证失败 |
| REF-004 | 非法置信度(<0) | confidence=-0.1 | 验证失败 |
| REF-005 | 空 key_insights | key_insights=[] | 创建成功（由业务层过滤） |

### 4.2 ReflectiveAgent 引擎

| 编号 | 用例 | 步骤 | 预期 |
|------|------|------|------|
| REF-101 | build_prompt 生成 | `agent.reflective._build_reflection_prompt(records)` | 返回 str，含 Episodic 格式 |
| REF-102 | process_result 成功 | JSON → process | 返回 ReflectionOutput, confidence>0.6 |
| REF-103 | process_result 低置信 | JSON with confidence=0.3 | 返回 None（过滤） |
| REF-104 | process_result 非法JSON | `"not json"` | 返回 None（解析失败） |
| REF-105 | process_result 缺字段 | `{"key_insights": []}` 无 confidence | 返回 None |
| REF-106 | reflect 路径A (有llm_fn) | `reflect(records, llm_fn=mock_fn)` | 自动调用→处理→返回结果 |
| REF-107 | reflect 路径B (无llm_fn) | `reflect(records, llm_fn=None)` | 返回 (prompt, record_ids) 元组 |
| REF-108 | 空记录 reflect | `reflect([], llm_fn=None)` | 返回 None 或空结果 |

### 4.3 合并写回

| 编号 | 用例 | 步骤 | 预期 |
|------|------|------|------|
| REF-201 | insight 合并 | key_insights → `_merge_to_semantic` | knowledge_agent.add_document 被调用 |
| REF-202 | preference 合并 | user_preferences → `_merge_user_preferences` | user_memory 更新 |
| REF-203 | rule 合并 | procedural_rules → `_merge_to_procedural` | 规则写入 |
| REF-204 | importance 更新 | importance_scores → `_update_rl_weights` | RL 权重调整 |
| REF-205 | 平台隔离写回 | platform="hermes" → preferences["hermes"] | 不覆盖其他平台 |

### 4.4 触发机制

| 编号 | 用例 | 步骤 | 预期 |
|------|------|------|------|
| REF-301 | 第 8 次触发 | store 8 次 | `_pending_reflection=True` |
| REF-302 | 第 7 次不触发 | store 7 次 | `_pending_reflection=False` |
| REF-303 | 触发后重置 | store 8 次 → 处理反思 | `_store_count=0`, `_pending_reflection=False` |
| REF-304 | 禁用时跳过 | reflection.enabled=false → store 8次 | 不触发 |

---

## 5. 适配器测试

### 5.1 Hermes Provider

| 编号 | 用例 | 步骤 | 预期 |
|------|------|------|------|
| ADP-001 | 导入 | `from adapters.hermes_provider import EchomindMemoryProvider` | 无报错 |
| ADP-002 | 初始化 | `EchomindMemoryProvider()` | 属性就绪 |
| ADP-003 | on_session_end 存储 | `on_session_end(messages)` | store 被调用，prefetch 产出 |
| ADP-004 | on_session_end 反思触发 | store 8次后的 on_session_end | 反思被调用（_hermes_llm_fn） |
| ADP-005 | _hermes_llm_fn 调用 | 发 prompt 到 localhost:9119 | 返回 LLM 响应文本 |
| ADP-006 | _hermes_llm_fn 网关故障 | 9119 不可用 | 返回空字符串，不崩溃 |

### 5.2 HTTP API

| 编号 | 用例 | 步骤 | 预期 |
|------|------|------|------|
| ADP-101 | 服务启动 | `python3 main.py` | 8005端口监听 |
| ADP-102 | 健康检查 | `GET /health` | `{"status":"ok","storage":"sqlite"}` |
| ADP-103 | 文档访问 | `GET /docs` | Swagger UI |
| ADP-104 | 错误请求 | POST 无 body | 422 错误 |

---

## 6. HTTP API 测试

### 6.1 /api/memory/store

| 编号 | 用例 | 步骤 | 预期 |
|------|------|------|------|
| API-001 | 正常存储 | POST 完整 body | 200, 返回 task_id |
| API-002 | 缺 user_id | POST 无 user_id | 422 校验失败 |
| API-003 | platform 参数 | POST platform="hermes" | 写入含 platform 标签 |
| API-004 | 长上下文 | context 100+ 条消息 | 不截断，正常存储 |

### 6.2 /api/memory/retrieve

| 编号 | 用例 | 步骤 | 预期 |
|------|------|------|------|
| API-101 | 正常检索 | POST task_context + user_id | 200, 返回记忆列表 |
| API-102 | platform 过滤 | POST platform="hermes" | 同平台优先 |
| API-103 | 空结果 | 不存在的 user_id | 200, 空列表 |

### 6.3 /api/reflect (v1.1.0)

| 编号 | 用例 | 步骤 | 预期 |
|------|------|------|------|
| API-201 | build prompt | POST user_id + count | `phase=build`, 返回 prompt 文本 |
| API-202 | process result | POST user_id + record_ids + llm_response | `phase=done`, 返回统计 |
| API-203 | 低置信度拒绝 | llm_response confidence=0.3 | 400, 拒绝 |
| API-204 | 非法 JSON | llm_response="garbage" | 400, 解析失败 |
| API-205 | 缺 llm_response（有 record_ids） | POST record_ids 无 llm_response | `phase=build`, 返回 prompt |

### 6.4 /api/memory/feedback

| 编号 | 用例 | 步骤 | 预期 |
|------|------|------|------|
| API-301 | 正向反馈 | POST feedback="positive" | 200, RL 权重更新 |
| API-302 | 负向反馈 | POST feedback="negative" | 200, RL 权重更新 |

### 6.5 /api/research/*

| 编号 | 用例 | 步骤 | 预期 |
|------|------|------|------|
| API-401 | 添加论文 | POST /api/research/paper | 200, 返回 id |
| API-402 | 添加笔记 | POST /api/research/note | 200, 返回 id |
| API-403 | 列出论文 | GET /api/research/papers | 200, 返回列表 |

---

## 7. 平台集成测试

### 7.1 Hermes Agent

| 编号 | 用例 | 步骤 | 预期 |
|------|------|------|------|
| INT-001 | 插件注册 | hermes 启动 → 检查 memory provider | echomind 已注册 |
| INT-002 | 自动存取 | 对话一轮 → 检查 context_memory | 新 session 写入 |
| INT-003 | 自动反思 | 8 轮对话 → 检查 reflections 表 | 新反思记录 |
| INT-004 | 零配置 | 新用户首次启动 hermes | 无需任何手动配置 |

### 7.2 OpenClaw / OpenCode / Claude Code

| 编号 | 用例 | 步骤 | 预期 |
|------|------|------|------|
| INT-101 | skill.yaml 解析 | 加载 skill.yaml | 工具定义正确 |
| INT-102 | HTTP 调用 | LLM 触发 tool_call → POST API | 返回结果正确 |

---

## 8. 回归测试清单

每次版本发布前必须通过的测试：

### v1.1.0 回归清单

- [ ] CORE-001~004: 初始化
- [ ] CORE-101~105: Store
- [ ] CORE-201~204: Retrieve
- [ ] CORE-301~304: RL 反馈
- [ ] DB-001~004: 存储初始化
- [ ] DB-101~105: reflections 表
- [ ] REF-001~005: ReflectionOutput 模型
- [ ] REF-101~108: ReflectiveAgent 引擎
- [ ] REF-201~205: 合并写回
- [ ] REF-301~304: 触发机制
- [ ] ADP-001~006: Hermes Provider
- [ ] ADP-101~104: HTTP API 基础
- [ ] API-201~205: /api/reflect
- [ ] INT-001~004: Hermes 集成

### 快速回归命令

```bash
cd /mnt/d/llm/echomind_memory.skill

# 1. Import 测试
python3 -c "
from core.memory_agent import MainMemoryAgent
from core.models.reflection import ReflectionOutput, ReflectionRecord
from core.reflective_agent import ReflectiveAgent
from core.storage.sqlite_store import SqliteStore
print('All imports OK')
"

# 2. 存储初始化测试
python3 -c "
from core.memory_agent import MainMemoryAgent
agent = MainMemoryAgent()
agent.enable_persistence()
agent.disable_persistence()
print('Storage init OK')
"

# 3. Store + Retrieve 测试
python3 -c "
from core.memory_agent import MainMemoryAgent
agent = MainMemoryAgent()
agent.enable_persistence()
agent.store('test','t1',[{'role':'user','content':'hello'}],platform='test')
r = agent.retrieve_for_task('hello','test',platform='test')
print(f'Retrieved: {len(r.get(\"retrieved_memories\",[]))} items')
agent.disable_persistence()
"

# 4. Reflection 模型测试
python3 -c "
from core.models.reflection import ReflectionOutput
o = ReflectionOutput(key_insights=['test'], confidence=0.8)
assert o.confidence == 0.8
try:
    ReflectionOutput(key_insights=['test'], confidence=1.5)
    print('FAIL: should reject confidence>1')
except:
    print('Model validation OK')
"

# 5. /api/reflect 端点测试 (需服务运行)
curl -4 -s http://localhost:8005/health && echo " Service OK"
curl -4 -s -X POST http://localhost:8005/api/reflect -H 'Content-Type: application/json' -d '{"user_id":"test","count":3}' | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Build: {d[\"phase\"]} prompt_len={len(d[\"prompt\"])}')" 2>/dev/null || echo "Service not running (OK if intentional)"
"

echo "Regression test complete"
```

---

## 附录: 版本变更记录

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0.0 | 2026-05-15 | 初始测试文档，覆盖 v1.1.0 全功能 |
| | | 将来版本在此追加... |

---

*本文件不参与 GitHub 发布，仅在本地维护。*