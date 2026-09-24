# EchoMind 更新日志

## v1.2.18 — 内部重构：Top-2 大文件拆分 (2026-09-23)

对两个最大模块进行结构性重构。**行为零变化**——全部调用点、导入路径与 DB 迁移经同名委派与重导保留；已通过对拍工具 + 全量测试（74 → 113，全绿）与生产库副本 schema 校验。

| 领域 | 改动 |
|------|------|
| **MainMemoryAgent（2959 → 2578 行）** | 无 self 依赖的叶子助手抽入可独立测试的模块：`core/scoring.py`（`score_base` / `parse_db_ts` / `freshness` / `gspo_cluster` / `diversify_top_k`）与 `core/lang_novelty.py`（`add_core_grams` / `core_term_novelty` / `jaccard_similarity` / `classify_relation`） |
| **模型** | `MemoryRecord` 下沉至 `core/models/memory_record.py`（从 `core.memory_agent` + `core.models` 重导，身份稳定），使 scoring 可引用它而不产生循环导入 |
| **子 Agent（2752 → 2578）** | 抽出依赖 self 的成块逻辑：`core/lifecycle.py`（`MemoryLifecycle`——Active→Stale→Archived + cognitive_pos 迁移）、`core/agents/evolution_agent.py`（`KnowledgeEvolutionAgent`——已知词表缓存 + 关系检测）、`core/agents/entity_agent.py`（`EntityAgent`） |
| **SqliteStore（2370 → 1972 行）** | 抽出静态 schema DDL 与纯行/键助手：`core/storage/schema.py`（`SCHEMA_VERSION` / `_MIGRATIONS` / `_PROFILE_TABLES` / `BASE_SCHEMA_SQL` / `PROFILE_INDEX_SQL`）、`core/storage/keys.py`（`stable_memory_key`）、`core/storage/rows.py`（`_normalize_row` / `_safe_json_loads` / null 默认常量）。DDL 逐字节一致 |
| **测试** | 新增 `tests/test_scoring.py`——39 项单测覆盖此前零覆盖的评分/GSPO/新颖度热点（74 → 113） |

**迁移：** 无——未改动 schema/表/列；DDL 字节、迁移顺序与 `PRAGMA user_version` 语义完全一致（对照真实库副本验证：user_version 11 不变，全部 14 张内存表 + 列一致）。

**兼容性：** 全部公共导入不变（`core.memory_agent.MainMemoryAgent/MemoryRecord`、`core.storage.sqlite_store.SqliteStore/stable_memory_key`、`core.__init__` 重导、`plugin.yaml` 入口）。重构为行为保持型。

---

## v1.2.17 — Review 复核与驱逐/退出加固 (2026-09-23)

对 v1.2.16 基线的后续复核轮。所有已实施的修复均对照真实 SQLite 引擎重验（15 项发现共 48 断言 + store/retrieve/query/delete 全链路冒烟，全部通过）；复核过程中浮出两个潜在数据完整性缺陷并已修复，剩下两项资源管理类发现也已落地。

| 领域 | 改动 |
|------|------|
| **TTL 绑定数缺陷（P1-6 续）** | `delete_expired` 的 `_expired()` 展开成含 **两个** `julianday(datetime('now', ?))` 的 CASE 表达式，但语句只绑定了一个 "-N days" 参数——凡同时具备 `last_access_at` 与 fallback 时间戳列的表（knowledge/experience/task）一旦有行超龄即抛 `ProgrammingError`。占位符改为编号 `?1`，单次绑定即可服务所有分支 |
| **Schema 门控查询（P0-1）** | `_query_rows` 以 `PRAGMA table_info` 门控 profile/project/origin/tags 谓词——此前带 tag 或 profile 的 `query_memory` 会在缺列的表（reflections 无 profile/tags，部分表无 origin_*）上静默跳过整个记忆类型。已验：带 tag 的全类型查询不再跳过任何表 |
| **稀疏标签预过滤复核（P1-1）** | 150 行仅 1 行带 `#audit` 的夹具：OR/AND/大小写/无 tags/全类型全部精确命中（json_valid 守护使遗留非 JSON tags 不会破坏 json_each） |
| **驱逐改延迟回收（P2-5）** | `main.py` call-agent 容量驱逐不再急切调用 `agent.shutdown()`——被逐 agent 可能正在其他线程中被调用；容量驱逐只把 agent 标记待回收，atexit 扫描在不可能再有调用竞态时才关闭。已验：被逐 agent 的 DB 在进程退出前保持打开、退出时被关闭 |
| **atexit join 整体预算（P2-6）** | `_cleanup_call_agents` 现在在**单一 30s 共享截止线**内清扫缓存 agent（每个 agent 分得剩余预算），而不是逐个 join（最多 8 agent × 每个至多 185s）。已验：8 个慢 agent 在 30.00s 内完成；传递给各 agent 的预算按预期递减 |
| **配置回退一致性复核（P0-2、P2-9）** | 隔离配置下：合法的 `batch_size: [7]` 在 `get()` 与 `get_section()` 均读 `[7]`；非法的 `max_daily: -3` 两侧都回退 `[5, 20]`；对同一 key 的运行时覆盖在两侧都生效——两条 API 不再可能读出不同结果 |
| **反思 batch 钳制复核（P1-9、P1-8）** | `_run` 把已抽取 batch 钳制到 `>= min_records`——已验证确定性 `batch_size=5` 抽取产出 `get_recent_episodic(count=6)`，到期反思不会因 sub-min_records 抓取而丢弃。correction 路径传入具体 batch |
| **跨用户状态隔离复核（P1-7）** | 用户 A 的一次 `retrieve_for_task` 不再触碰用户 B 的 memory_states |
| **删除路径复核（P1-2/3/4、P2-8）** | 反思重放幂等（首写胜出）；按 profile 的 `delete_user_memories` 保留其他 profile 的行并级联该 profile 的 context_archive；`delete_expired` 级联 memory_states/evolution/archive 同时保留新鲜行 |
| **反思 knowledge 持久化复核（P1-12）** | `store_reflection_knowledge` 写入租户隔离（`user_id`、`domain=insight`、`origin_client=reflection`）且**重启后仍在**的行，并失效 core-term 缓存（P2-12 重置也一并验证） |

**Migration:** 无。行为说明：(1) 容量驱逐原先立即关闭 DB——现改为推迟到进程退出，避免被逐 agent 的并发调用撞上已关闭连接；内存在进程退出时回收。(2) v1.2.16 中 aged knowledge/experience/task 行在 `delete_expired` 上会抛的 `ProgrammingError` 已消除——部署中在日志见过此类错误的现已修复。

---

## v1.2.16 — 全数据链路审计修复：退出收口、租户隔离、TTL 与完整性 (2026-09-22)

本轮精读记忆全数据链路（存储 → 读取 → 删除 → 适配），跨各层修复 32 项缺陷——反思/退出路径收敛为单一契约，知识/标签/状态机检索做到租户正确，删除级联一致，配置与工具调用的加固消除了静默失败模式。

| 领域 | 改动 |
|------|------|
| **退出收口统一（P0-1、P1-8/9/10/13）** | `MainMemoryAgent.shutdown()` 成为四个入口（main.py atexit、hermes_provider、http lifespan、call-agent 淘汰）的统一退出契约：先冲刷待反思到其记录的 user+profile，再 join 反思线程（上限按 LLM 重试预算 `max(30, 3×timeout+5)` 秒），最后禁持久化。修复：atexit 路径调用 `_trigger_auto_reflection(platform=...)` 缺必填 `user_id` → 每次退出必抛 TypeError 且被静默吞掉；HTTP lifespan 从不 join 反思线程（每次重启丢反思）；固定 30s join 在慢 LLM 重试超 30s 时放弃反思。`store()` 的 correction 与计数路径都改为传入已抽取 batch（`_get_adaptive_batch`），`_run` 把 `batch_size` 钳制到 ≥ `min_records`——batch 与 min_records 相矛盾（约 1/8 反思触发被确定性丢弃）在单一改点闭环 |
| **稀疏标签检索（P1-1）** | tags 此前在 `LIMIT ?` 之后才做 Python 侧过滤——查询稀疏 tag（150 行中只有 1 行）返回空。现把 LIKE 预过滤（`json_each` 元素 + 原始 JSON 串，大小写不敏感）下推进 SQL、在 LIMIT 之前执行，fetch 乘数降至 2× |
| **reflections profile 级删除（P1-3）** | `delete_user_memories` 按 profile 删除时不再误删该用户所有 profile 的 reflections（该表无 profile 列）；profile 级删除跳过它，user 级删除保持全量语义 |
| **删除级联一致性（P1-4、P2-8）** | `delete_expired` 现在与 `delete_memory` 一样级联清理 `memory_states`、`knowledge_evolution`、`context_archive`；HTTP 单条 DELETE 改走 `MainMemoryAgent.delete_memory`，同时从内存快路径（knowledge `_content_index`/store、experience 索引、context/task store）移除——此前删除的记录在重启前仍可被检索 |
| **TTL 时间戳对齐（P1-5、P2-18）** | `delete_expired` 以字符串比较 ISO 与 SQLite 时间戳，与截止日同日的存量 ISO 行被永久漏删；现两侧统一用 `julianday()`，两格式解析一致正确 |
| **状态机扫描隔离（P1-7）** | `_update_memory_states` 的 SELECT 加 `WHERE user_id = ?`（四表）+ `ORDER BY created_at DESC LIMIT ?`——任一用户的检索不再可能归档另一用户的记忆；状态转换批量放入单事务（`_migrate_cognitive_pos` 外置，因其私有 commit） |
| **内存写前镜像（P1-11）** | `store()` 原先在 DB 提交之后才把 knowledge/experience 镜像进内存——内存侧后置失败会留下"DB 已写、内存未镜像"半态并返回 False；现内存镜像在 DB 事务之前完成，副作用链原子化 |
| **反思知识持久化与租户隔离（P1-12、P2-7）** | 反思产出的 insights/knowledge/rules 此前 metadata 缺 `user_id` → 落入共享 "default" 桶（任意用户可检索）且从不持久化、重启即失。`_merge_semantic`/`_procedural` 现携带真实 `user_id`，`store_reflection_knowledge` 以租户维度 id（`md5(user \x00 content)`、metadata 含 user/domain/epistemic 模式）幂等落库（ON CONFLICT: access_count+1），并失效 core-term 缓存 |
| **反思幂等（P1-2）** | `save_reflection` 由 `INSERT OR REPLACE`（同 id 重放整行覆盖）改为 `INSERT OR IGNORE`——首次写入获胜 |
| **检索后内存 last_access 回写（P1-6）** | knowledge/experience 内存条目在检索时同步刷新 `last_access_at` 与 DB 一致——归档状态与 freshness 打分共用一个来源 |
| **配置一致性与打包（P2-9、P2-16）** | `get_section()` 对 schema 无效键改以 `FALLBACK_CONFIG` 值替补（此前 pop → 键 MISSING，与 `get()` 不一致）；bundled keywords/language YAML 先走 `importlib.resources`、再走源码树——pip 安装的 wheel 不再静默退化为空 domain 检测（`package_data` 已含） |
| **RL 并发与守卫（P2-13、P2-14）** | `add_feedback` 的桶交换（`del`+`setdefault`）移入锁内；`_update_weights` 增加 n==0 守卫（直接调空桶不崩 ZeroDivision） |
| **MCP/HTTP 加固（P2-15、P2-10、P2-11、P2-17）** | `turn` 用 `_safe_int` 解析（`"abc"` 不再泄漏 ValueError）；autoreflection/archive 错误响应返回通用 `detail`（不再泄漏路径/SQL）；CORS 允许 DELETE；`main.py` call-agent 缓存上限为 8 并优雅关闭淘汰 |
| **reload 缓存失效（P2-12）** | `refresh_config` 与其它派生缓存一并清空 `research_agent._domain_cache` |

**迁移：** 无——无新表或新列。行为说明：(1) 反思知识现持久化且租户隔离；此前仅驻留内存的 insights 不做回填。(2) 状态机转换不再跨用户边界。(3) profile 级删除不影响其他 profile 的 reflections。验证：每项均配套 E2E/回归检查——稀疏标签、profile 删除、TTL 级联、内存删除、跨用户状态扫描、重启持久化、半写回滚、RL 桶交换、bundled YAML 加载、配置回退语义、HTTP 错误不透传。

---

## v1.2.15 — 深度审计修复：死路径复活、租户隔离与 MCP 串号修复 (2026-09-21)

外部深度审计轮次：四项高危发现曾使三大宣传能力（自动反思、生命周期状态机、知识进化检测）在主路径上成为死代码——全部发现均已复现、修复并通过回归/集成验证。另含默认用户身份统一与 MCP 客户端串号修复。

| 领域 | 改动 |
|------|------|
| **自动反思死路径** | `_trigger_auto_reflection._run` 在 RHS 对闭包同名 `batch_size` 自赋值——每次自动反思必抛 `UnboundLocalError` 且被 except 静默吞掉 → 改用独立局部名（`bs`）；每个已调度的反思现在真正执行 |
| **生命周期状态机死路径** | 状态扫描 SELECT 引用了仅存在于 `user_memory` 表的 `last_updated` 列——首表即抛 `no such column` 且 debug 静默，Active→Stale→Archived 转换恒为零 → 去掉该列（`_freshness` 本就按 `last_access_at` → `created_at` 回退），扫描失败路径升为 warning |
| **知识进化死路径** | `_detect_knowledge_evolution` 在新条目保存+镜像之后才运行，新条目自身必在候选集且 Jaccard=1.0，循环后自引用检查（`best_id == knowledge_id`）使检测恒为空操作 → 自身条目改在候选循环内排除 |
| **进化溯源** | `store()` / `POST /api/memory/store` / MCP `echomind_store` 接受 `turn` 轮次索引，透传至进化记录行（`origin_turn`——此前恒为 0） |
| **GSPO 改为可选（行为变化）** | 聚类聚合把五维 RL 权重算出的分数按簇覆写为同一几何均值且默认开启 → 改为可选（`rl.gspo.enabled`，默认 **false**），且空 `session_id` 不再把全部同源记录并入一簇 |
| **知识主键加租户维度** | `kb_id` 原为纯内容 md5——用户 B 的同内容插入直接 UPDATE 覆盖用户 A 的行（`user_id=excluded.user_id`）→ 哈希加入租户维度（`user_id \x00 content`），内存侧内容哈希去重（`knowledge_agent.add_document`、reload 索引）同步隔离 |
| **MCP 身份隔离** | HTTP `/mcp` 端点单进程服务多客户端，单一模块级全局使客户端 B 的调用被记到最后一个 initialize 的客户端名下 → HTTP 连接按 `Mcp-Session-Id`（或 `X-Session-Id`）键控身份，`X-Client-Name` 提供按请求覆盖；stdio 网关保持模块全局（每连接一进程） |
| **热路径 LLM 门控** | `_detect_research_domain` 的同步 LLM 回退挂在检索路径上——60s 超时 × 3 次尝试，最坏约 181s → 改为可选（`retrieval.llm_domain_detect`，默认 **false**；关键词匹配 + "general" 兜底保留），单次调用硬限 5s |
| **MCP 端点鉴权** | `POST/GET /mcp` 是全量记忆读写面上仅有的无鉴权路由 → 现在与 `/api/*` 一样要求 `X-API-Key`（未配置 api_key 时保持开放，与 `verify_api_key` 一致）；stdio→HTTP 桥接本就发送该 key |
| **默认用户身份统一** | 未收到显式 `user_id` 的入口现在把记忆归入配置的顶层 `default_user`（开源默认 `"default"`），而非按会话 id 或共享 `"cli"`：`mcp_common._default_user_id()` 替换六处 `"cli"`/`""` 回退，`hermes_provider` 不再按会话 id 碎片化同一用户的记忆（真实 DB 中观察到 10 个此类身份），`main.py` 八处回退统一走同一 helper。`clientInfo` 推断保持仅溯源用途（`origin_client`）；身份与来源是独立维度 |

**迁移：** 无——无新表或新列。行为说明：(1) `rl.gspo.enabled` 默认 false；设 true 可恢复聚类聚合。(2) `retrieval.llm_domain_detect` 默认 false；设 true 可重新启用 LLM 语义域名回退。(3) 存量 `k:` 知识 id 不重算主键——新 id 插入会为此前被覆盖的行产生一次性重复，可手动清理。(4) MCP 客户端连接已配置 api_key 的服务时需在 `/mcp` 发送 `X-API-Key`（stdio 网关无需改动）。验证：74 项回归测试 + 定向集成检查（状态转换、带 `origin_turn` 的进化记录、跨用户去重、按会话 MCP 身份）。

---

## v1.2.14 — 来源追溯：origin 追踪、tags 过滤与结构化查询 (2026-09-19)

每条记忆记录现在携带自描述来源信封——**传输方式**（mcp/http/hermes/cli）+ **来源客户端**（claude-code/opencode/...）+ project + tags + 捕获时间——并可按这些谓词的任意组合，从任何受支持入口检索。

| 领域 | 改动 |
|------|------|
| **tags 来源** | `echomind_store` / `store()` 接受调用方 `tags`（优先）；自动主题 tags 补足（保留原文大小写、casefold 去重、≤12 个、单标签 ≤32 字符）。`echomind_retrieve` / `retrieve_for_task` 接受 `tags` + `tags_match_all`（默认 OR，可选 AND）——此前 agent 级 tags 过滤已实现但从未被调用 |
| **origin 列** | 迁移 v10 为 knowledge/experience/task/research/transcript 增加 `origin_platform`（传输方式）与 `origin_client`（来源客户端）（context/reflections 补 `origin_client`，legacy `platform` 列保留双写），带复合索引；空默认值保证旧数据在任何 origin 过滤下可见 |
| **MCP client 推断** | `initialize` 握手的 `clientInfo.name` 被捕获（归一化）为连接的 `origin_client`——来自 Claude Code 的存储自动记录为 `mcp`/`claude-code`，调用方零成本；显式参数覆盖 |
| **跨源软降权** | origin 与查询传输方式不同的记录降权 ×0.5（配置 `retrieval.origin_cross_soft_enabled` / `origin_cross_soft_penalty`，可关）；无 origin 的旧数据不受罚 |
| **来源信封** | `store()` 将完整信封（`schema: envelope-v1`）快照进 task/knowledge/experience 的 metadata；`envelope_from_record` 从平铺 origin 字段重建兜底，信封出现前的记录仍可渲染 |
| **来源可见** | markdown 归档的 knowledge/experience/task 每行增加 Origin 列——`[2026-09-19][mcp/claude-code][projA][代码习惯,coding]`；MCP `echomind_retrieve` 输出每条带 `origin=` |
| **echomind_query** | 新增结构化来源查询（MCP 工具 + `POST /api/memory/query` + `query_memory` 技能 + CLI `query` 子命令）：project / tags（OR/AND）/ origin_client / origin_platform / 日期区间（含边界；一天 = `date_from=date_to`）/ 记忆类型 的精确谓词，无相关性评分，跨 7 张记忆表合并 |
| **健壮性** | 全部新过滤为绑定参数（无 SQL 字符串拼接）；未知 `memory_type` 抛 ValueError → HTTP 400；无 origin 列的表跳过而非失败 |

**迁移：** v10 在首次连接时自动执行（幂等 `ADD COLUMN` + `CREATE INDEX`，BUSY 重试）。不改动数据；旧数据保持现有召回。排序说明：跨源软降权会改变跨传输查询的排序——设 `origin_cross_soft_enabled: false` 可恢复。

---

## v1.2.13 — 深度审查加固：隔离、并发与评分一致性 (2026-09-13)

三轮深度代码审查加固——租户隔离、RL/事务并发、检索与评分语义统一——排序行为变化见下方说明。

| 领域 | 改动 |
|------|------|
| **租户隔离** | 知识去重（`search_knowledge_by_content`）按 `user_id`/`profile` 隔离——任一用户的去重不再命中（或因此静默跳过）其他用户的内容；`record_feedback` 在 Hermes `call()` 路径透传 `profile`（此前跨写到 default profile 的 RL 权重） |
| **删除级联与 profile 安全** | `delete_user_memories` 不再跨 profile 误删 `session_transcripts`（仅 `reflections` 无 profile 列）；单条与用户级删除级联清理 `memory_states`、`knowledge_evolution`、`hit_history`、`reflection_daily_count`（孤儿行与健康统计虚高消除） |
| **RL 读并发** | `load_weights_for_user` 返回生效权重快照，评分使用该快照；`get_current_weights` 加锁——"先 load 后读"窗口（一个用户可能用另一个用户的权重评分）已关闭 |
| **事务内 IO** | LLM 实体抽取移出 `store()` 写事务——`BEGIN IMMEDIATE` 写锁不再跨网络 IO 持有（此前 LLM 超时会阻塞所有写者并回滚整批记忆） |
| **反思配额原子化** | 预扣-退还：每日配额由单条原子条件自增强制（跨进程 TOCTOU 关闭）；失败反思（解析错误/低置信度）退还配额槽位，不再消耗配额 |
| **评分统一（行为变化）** | 新增 `_score_base` 按来源归一化加权信号：freshness 为唯一 recency 杠杆（knowledge 不再双重衰减）、domain boost 改乘性、`trust_score` 开始驱动 experience 排序（固定常数 `recency_multiplier` 移除） |
| **检索一致性** | `max_results` 在 `retrieve_for_task` 内生效（此前 core 恒截 8，HTTP `max_results>8` 静默无效）；各入口 platform 默认值显式化（`http`/`hermes`/`mcp`）；内存上下文与 DB 行使用同一 key |
| **多样性选择** | `_diversify_top_k` 改两遍分桶：每个域保证一个代表（此前密集单域可占满全部名额） |
| **配置校验** | 校验不再删除用户 YAML 数据（被拒键在读取期回退）；list/tuple 元素逐个校验（负数 `max_daily` 列表此前静默禁用反思）；配置热重载清空全部派生缓存并热刷新每日限额；`get_config_manager` 按路径缓存实例 |
| **安全** | `/api/config/parameter` 增加 section 白名单并保护 `api_key` 不可被运行时改写；未知记忆类型返回 400（而非 500）；MCP 通知返回空 202 响应体 |
| **生命周期与可观测** | `call()` agent 退出前触发并 join 待处理反思，会话 reset 时清除 pending 反思；数据丢失与 LLM 配置同步失败改为 warning 日志（此前 debug 静默） |
| **健壮性与测试** | 回退引擎归一化 list 形 LLM 字段（合法但形状不合规的响应不再被丢弃）；chunking 对超长单行强制硬上限；CLI 增加 action 白名单、stdin schema 校验与 try/finally 清理；`tests/test_api.py` 使用临时 DB（此前会触碰真实 `~/.echomind/memory.db`）；死代码清理（`_pending_reflection_event`、`old_cols`、chunking 重复分支） |

**说明（行为变化）：** 评分统一后排序结果变化——knowledge 按文档 half-life 速度老化（此前二次方）、experience 的 recency 改为真实时间衰减、`trust_score` 参与 experience 排序。现有 RL 权重仍然有效；建议观察检索质量 1–2 周后再校准。`retrieval.recency_multiplier` 已废弃（配置模板中注释保留；取消注释无效果）。

**无需迁移：** 无新表或新列；全部为就地代码与配置注释更新。

---

## v1.2.12 — 算法优化：核心词新颖比例、RL 显著性验证与分块保护 (2026-08-26)

算法优化——核心词新颖比例、候选显著性验证、代码块安全分块——作为零 LLM 快速启发式融入热路径。

| 领域 | 改动 |
|------|------|
| **核心词新颖比例** | `_core_term_novelty` / `_known_core_terms` 提取 3-4 字 CJK 核心 n-gram，并门控 `_detect_knowledge_evolution`：与旧句高度重叠但含全新概念的句子（novelty ≥ 0.85）不再被整句 Jaccard 误判为 `replaces`/`enriches` |
| **已知词表构建** | 优先内存 `knowledge_agent.store`，条目低于 `_MIN_TERM_STORE_SIZE`（冷启动/驱逐）时回退 SQL 精确查询（`get_knowledge_content`），写入/驱逐后缓存失效——取代 AEIS 不完整的 `query_nodes(limit=80)` 采样 |
| **RL 显著性验证** | `verify_improvement(hits_bool, baseline_bool)` 采用二项标准误（success > baseline + 2·SE）；`hit_history` SQLite 表持久化二值命中；`record_feedback` 记录命中并每 50 次 feedback 触发验证，失败走保守阶梯处置（首次减半 LR） |
| **代码块安全分块** | `chunk_text()`（core/chunking.py）整体提取围栏代码块，绝不拆散内部空行，超长块按行组切分；`add_research_note` 保留 2000 字符截断并分块，加 `chunk:i` 可追溯标签 |

**说明：** `hit_history` 为新表，不影响存量数据。新颖门控为软信号，不取代 LLM 关系分类。

---

## v1.2.11 — 项目作用域与 Hermes 分身修复 (2026-08-24)

修复 MCP（DSH/Zcode）与 Hermes 路径的跨 agent 记忆污染：让 `project` 成为真实可用的作用域键，并恢复 Hermes 分身（profile）之间的隔离。

| 领域 | 改动 |
|------|------|
| **项目作用域** | 顶层配置键 `default_project` 现在于运行时被消费（`ConfigManager.get_top_level`），并由 MCP 网关在客户端未传入 project 时用于解析默认项目——不再是死配置，MCP 流量也不再静默落入共享的 `"default"` 命名空间 |
| **Hermes 分身隔离** | `initialize()` 优先使用宿主传入的 `agent_identity`（活跃 Hermes profile/分身名）作为记忆 `profile`；`_derive_profile(hermes_home)` 仅作兜底，且 `project` 不再硬编码为 `"hermes"` |
| **可观测性** | `retrieve_for_task`/`store` 在 `project` 仍为 `"default"` 时发出 warning，使无作用域写入可被发现 |
| **knowledge 去重修复** | knowledge 主键由 task 维度改为 content 维度（`k:<content_hash>`），`ON CONFLICT(id)` 真正生效，修复 knowledge_memory 随任务无限膨胀及去重失效的问题 |
| **preferences 双嵌套修复** | `store()` 持久化原始嵌套 preferences 而非 `get(platform=)` 展开的扁平值，`_merge_platform_prefs` 对已嵌套输入整体采纳，避免 `_default` 桶被平台污染及双嵌套 |
| **feedback 透传 profile** | `/api/memory/feedback`（HTTP 与 MCP）透传 `profile`，RL 权重按 profile 隔离，避免分身在 RL 层互相污染 |
| **关键字实体抽取 fallback** | FALLBACK_CONFIG 补充 `entities.technologies` 段，使无 LLM 时的关键字实体抽取有数据源（此前恒空） |

**说明：** `platform` 保持软权重（同平台 ×1.0、跨平台 ×0.5），仅作用于 context 源；knowledge/experience/task 的作用域为 `user_id + project + profile`。本次发布无 schema 迁移。

> 已知低影响问题暂不修复（待专项重构）：`session_id` 在 context（稳定 key）与 task/experience（原始 id）之间语义不一致，但不影响检索正确性；`sync_to_code_project` 导出未按 project 过滤。

---

## v1.2.10 — 算法优化轮 (2026-08-15)

算法优化轮：补齐反思闭环，并强化 RL 学习路径的按用户隔离。

| 领域 | 改动 |
|------|------|
| **反思闭环** | `_reflective_fallback.py` 实现 4 个 `_merge_*`/`_save_reflection` 桩并消费 `_process_reflection` 产物 (P1-A)；新增与 `decay_all` 对称的正向 `_reinforce_weights` 臂，并修复 few-shot 提示词构建 bug (P1-B) |
| **RL 信用分配** | `_update_weights` 只对 mapped 源真实出现的维度给予方向性增量 (P2-B)——此前 softmax + M-4 中性回退会稀释每次正向反馈，任何维度份额都无法有效抬升 |
| **归一化不变量** | 声明 `_WEIGHT_INVARIANT_UPDATE/DECAY = "linear"` 并把周期性反发散 `decay_all` 接入 `_update_weights` (P3-A)；修复 `decay_all` 先归一化后 clamp 的顺序（range 不变量） |
| **日限额 per-user + 持久化** | 反思日限改为按 `(user_id, 日期)` 计并持久化到 SQLite（`reflection_daily_count`），重启后仍生效 (P5-B) |
| **RL meta-state per-user** | LR/探索调度、history、发散快照、累计计数全部按用户键控——一个用户的反馈不再推进另一个用户的学习轨迹 (P5-A) |
| **存储索引** | 补幂等连接/查找索引（knowledge 内容、task/experience 按 user+created、reflections 按 user+created）(P6-A) |

**测试：** 102 通过（含新增日限、meta-state 隔离、反思闭环、RL 投影、稳定 ID、存储、新鲜度回归测试）。

**补充审计轮（发布后修复）：**
- **HIGH-1**：`/api/reflect` 将 `user_id` 传给 `_check_daily_limit`，命中日限时返回 429 而非 TypeError-500（恢复「日限/解析失败」状态区分）。
- **日限权威读取 (MED-2)**：计数改为每次从 store 重新读取（不再每实例 seed 一次），HTTP 与 Hermes 共享同一 DB 时不再各自跑满限额（2×~N× 超发）。新增跨实例可见性回归测试。
- **RL 空信用 no-op (MED-3)**：`retrieved_memories` 为空（空 `present_set`）的反馈不信用任何维度，也不再推进实际未挣得的探索调度。
- **RL 线程安全 (MED-5)**：load/decay/flush 由 per-optimizer 锁串行化。
- **反思单点持久化 (MED-6)**：删除 `_run` 重复 `auto:` 保存；fallback `_process_reflection` 为唯一写者，与 native 引擎对称。
- **反思 id 唯一性 (MED-7)**：id 改用 `time.time_ns()`——不再有同秒 PK 撞车/覆盖。
- **混合语言分词 (MED-8)**：无论整体语言检测结果都提取 CJK bigram，混合中英串（及 kana/hangul）不再在知识演化 Jaccard 中丢弃全部汉字。
- **experience 相关性 vs 频率 (MED-9)**：`find_similar_tasks` 的相关性改为查询 token 覆盖率，不再是伪装的频率函数——frequency 不再被二次计入。
- **偏好 platform 透传 (MED-10)**：反思产出的偏好落入平台专属 bucket，而非仅 `_default`。
- **低置信度丢弃 (P1-A #9)**：低于阈值的 fallback 反思返回 `None`（既不持久化也不耗配额），与 native 引擎一致。
- **打磨**：剪枝过期日限缓存键 (#7)；删除冗余 `task_memory(user_id)` 索引 (#10)；提升模块级 import (O1)；收拢死代码 `_compute_rcw_advantages` 包装并更正 clamp/decay 注释 (F8/F4/F5)。

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
