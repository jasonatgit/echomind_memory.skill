# EchoMind Changelog

## v1.2.18 — Internal Refactor: Top-2 File Split (2026-09-23)

Structural refactor of the two largest modules. **No behavior change** — every existing call site, import path and DB migration is preserved through same-named delegates and re-exports; verified by a parity harness + the full suite (74 → 113 tests, all green) and a production-DB-copy schema check.

| Area | Change |
|------|--------|
| **MainMemoryAgent (2959 → 2578 lines)** | Extracted the self-free leaf helpers into independently-testable modules: `core/scoring.py` (`score_base` / `parse_db_ts` / `freshness` / `gspo_cluster` / `diversify_top_k`) and `core/lang_novelty.py` (`add_core_grams` / `core_term_novelty` / `jaccard_similarity` / `classify_relation`) |
| **Models** | `MemoryRecord` sunk to `core/models/memory_record.py` (re-exported from `core.memory_agent` + `core.models`, identity stable) so scoring can reference it without a circular import |
| **Sub-agents (2752 → 2578)** | Extracted the self-bound cohesive blocks: `core/lifecycle.py` (`MemoryLifecycle` — Active→Stale→Archived + cognitive_pos migration), `core/agents/evolution_agent.py` (`KnowledgeEvolutionAgent` — known-term corpus cache + relation detection), `core/agents/entity_agent.py` (`EntityAgent`) |
| **SqliteStore (2370 → 1972 lines)** | Extracted the static schema DDL and pure row/key helpers: `core/storage/schema.py` (`SCHEMA_VERSION` / `_MIGRATIONS` / `_PROFILE_TABLES` / `BASE_SCHEMA_SQL` / `PROFILE_INDEX_SQL`), `core/storage/keys.py` (`stable_memory_key`), `core/storage/rows.py` (`_normalize_row` / `_safe_json_loads` / null-default constants). DDL is byte-for-byte identical |
| **Tests** | New `tests/test_scoring.py` — 39 unit tests for the previously ZERO-coverage scoring/GSPO/novelty hot spots (74 → 113) |

**Migration:** none — no schema/tables/columns changed; DDL bytes, migration order and `PRAGMA user_version` semantics are identical (verified against a copy of the live DB: user_version 11 unchanged, all 14 memory tables + columns identical).

**Compatibility:** all public imports unchanged (`core.memory_agent.MainMemoryAgent/MemoryRecord`, `core.storage.sqlite_store.SqliteStore/stable_memory_key`, `core.__init__` re-exports, `plugin.yaml` entry). Refactor is behavior-preserving.

---

## v1.2.17 — Review Verifications & Eviction/Join Hardening (2026-09-23)

Follow-up review round on the v1.2.16 baseline. Every implemented fix was re-verified against the live SQLite engine (48 assertions across 15 findings + full-chain store/retrieve/query/delete smoke, all green); two latent data-integrity bugs surfaced by the verification were fixed, and the two remaining resource-management findings were implemented.

| Area | Change |
|------|--------|
| **TTL binding-count bug (P1-6 follow-up)** | `delete_expired`'s `_expired()` helper expanded into a CASE expression containing TWO `julianday(datetime('now', ?))` occurrences, but the statement was executed with ONE bound "-N days" parameter — every table with both `last_access_at` and a fallback timestamp column (knowledge/experience/task) raised `ProgrammingError` as soon as any row aged. The placeholder is now numbered (`?1`), so a single binding serves every branch |
| **Schema-gated queries (P0-1)** | `_query_rows` gates profile/project/origin/tags predicates on `PRAGMA table_info` — before, tagged or profile-scoped `query_memory` silently dropped whole memory types whose table lacked those columns (reflections has no profile/tags, several have no origin_*). Verified: tagged all-types query no longer skips any table |
| **Sparse-tag prefilter verified (P1-1)** | 150-row fixture with a single `#audit` row: OR/AND/case-insensitive/untagged/all-types all match exactly (json_valid guard keeps legacy non-JSON tags from breaking json_each) |
| **Double-write eviction (P2-5)** | `main.py` call-agent capacity eviction no longer calls `agent.shutdown()` eagerly — the victim may still be mid-call on another thread. Capacity eviction tags the agent for reclamation; the atexit sweep closes tagged agents when no further calls can race. Verified: evicted agent's DB stays open until exit; atexit closes it |
| **Bounded atexit join budget (P2-6)** | `_cleanup_call_agents` now sweeps the cached agents under ONE shared 30s deadline (each agent takes the remaining budget), instead of joining up to 8 agents × up to 185s each. Verified: 8 slow agents finish in 30.00s; budgets passed to agents decrease as expected |
| **Config fallback agreement re-verified (P0-2, P2-9)** | With an isolated config: a valid `batch_size: [7]` reads `[7]` from both `get()` and `get_section()`; an invalid `max_daily: -3` falls back to `[5, 20]` in both; a runtime override on the same key wins in both — the two APIs can no longer disagree |
| **Reflection batch clamp re-verified (P1-9, P1-8)** | `_run` clamps the drawn batch to `>= min_records` — verified a deterministic `batch_size=5` draw yields `get_recent_episodic(count=6)`, so a due reflection is never dropped by an under-min_records fetch. The correction path passes a concrete batch |
| **Cross-user state isolation re-verified (P1-7)** | A `retrieve_for_task` by user A leaves user B's memory_states untouched |
| **Delete paths re-verified (P1-2/3/4, P2-8)** | Reflection replay is idempotent (first write wins); profile-scoped `delete_user_memories` keeps other profiles' rows and cascades that profile's context_archive; `delete_expired` cascades memory_states/evolution/archive while preserving fresh rows |
| **Reflection knowledge persistence re-verified (P1-12)** | `store_reflection_knowledge` writes tenant-scoped (`user_id`, `domain=insight`, `origin_client=reflection`) rows that SURVIVE restart, and invalidates the core-term cache (P2-12 reset verified too) |

**Migration:** none. Behavior notes: (1) capacity eviction used to close DBs immediately — it now defers to exit, so concurrent callers on an evicted agent can't hit a closed connection; memory is reclaimed at process exit. (2) `delete_expired` prevented the `ProgrammingError` it would have raised on aged knowledge/experience/task rows in v1.2.16 — deployments that saw those errors in logs should be fixed now.

---

## v1.2.16 — Full-Data-Path Audit Fixes: Shutdown Unification, Tenancy, TTL & Integrity (2026-09-22)

This round deep-read the full memory data path (store → read → delete → adapter). 32 findings were fixed across every layer — the reflection/exit path is now one unified contract, knowledge/tag/state-machine retrieval is tenancy-correct, deletion cascades consistently, and config/tool-call hardening removes silent failure modes.

| Area | Change |
|------|--------|
| **Shutdown unification (P0-1, P1-8/9/10/13)** | `MainMemoryAgent.shutdown()` is now the single exit contract for all four entrypoints (main.py atexit, hermes_provider, http lifespan, call-agent eviction): flush pending reflections to their recorded user+profile, join the reflection thread bounded by the LLM retry budget (`max(30, 3×timeout+5)`s), then disable persistence. Fixes: the atexit path called `_trigger_auto_reflection(platform=...)` without the required `user_id` → guaranteed TypeError swallowed on every Hermes exit; the HTTP lifespan never joined the reflection thread (reflections dropped on every restart); the fixed 30s join abandoned reflections when a slow LLM retried past 30s. `store()` correction and count paths now pass the extracted batch (`_get_adaptive_batch`), and `_run` clamps `batch_size` up to `min_records` — the batch-vs-min_records contradiction that made ~1/8 of reflection triggers deterministically drop records is closed at a single point |
| **Sparse-tag retrieval (P1-1)** | Tags were filtered in Python AFTER `LIMIT ?`, so a query for a sparse tag (1 row in 150) returned nothing. A LIKE pre-filter (`json_each` element + raw JSON string, case-insensitive) is now pushed into the SQL before the limit, with the fetch multiplier reduced to 2× |
| **Profile-scoped reflections delete (P1-3)** | `delete_user_memories` for a profile no longer wipes every profile's reflections (the table lacks a profile column); profile-scoped deletes skip it, user-wide deletes keep the full semantics |
| **Delete-cascade parity (P1-4, P2-8)** | `delete_expired` now cascades to `memory_states`, `knowledge_evolution` and `context_archive` exactly like `delete_memory`; the HTTP single-record DELETE now routes through `MainMemoryAgent.delete_memory`, which also drops the record from the in-memory fast paths (knowledge `_content_index`/store, experience indices, context/ task stores) — previously a deleted row stayed retrievable until restart |
| **TTL timestamp parity (P1-5, P2-18)** | `delete_expired` compared ISO and SQLite timestamps as STRINGS, so legacy ISO rows on the same calendar day as the cutoff permanently escaped deletion; comparison now uses `julianday()` on both sides, which parses both formats correctly |
| **Memory-state scan scoping (P1-7)** | `_update_memory_states` SELECTs now carry `WHERE user_id = ?` (four tables) plus `ORDER BY created_at DESC LIMIT ?`, so one user's retrieval can no longer archive another user's memories; state transitions batch into one transaction (`_migrate_cognitive_pos` stays outside — it commits privately) |
| **In-memory write-ahead mirror (P1-11)** | `store()` mirrored knowledge/experience into memory AFTER the DB commit, so a late in-memory failure left DB-written/unmirrored half-state returning False; the memory mirror now completes BEFORE the DB transaction, so the side-effect chain is atomic |
| **Reflection knowledge persistence & tenancy (P1-12, P2-7)** | Reflection-derived insights/knowledge/rules were merged with metadata lacking `user_id` → they landed in the shared "default" bucket (retrievable by EVERY user) and were never persisted, vanishing on restart. `_merge_semantic`/`_procedural` now carry the real `user_id`, and `store_reflection_knowledge` persists tenant-scoped (`md5(user \x00 content)` ids, metadata with user/domain/epistemic mode) idempotent rows (ON CONFLICT: access_count+1) with the core-term cache invalidated |
| **Reflection idempotency (P1-2)** | `save_reflection` switched from `INSERT OR REPLACE` (whole-row overwrite on same-id replay) to `INSERT OR IGNORE` — first-write wins |
| **Retrieved last_access in RAM (P1-6)** | knowledge/experience in-memory entries got their `last_access_at` refreshed on retrieval to match the DB, so archived state and freshness scoring share one source |
| **Config consistency & packaging (P2-9, P2-16)** | `get_section()` now substitutes `FALLBACK_CONFIG` values for schema-invalid keys (previously popped → section MISSING, disagreeing with `get()`); bundled keywords/language YAMLs load via `importlib.resources` first, then the source tree — pip-installed wheels no longer silently degrade to empty domain detection (`package_data` includes them) |
| **RL concurrency & guards (P2-13, P2-14)** | `add_feedback` bucket swap (`del`+`setdefault`) moved inside the lock; `_update_weights` guards n==0 (no ZeroDivision on empty-bucket direct calls) |
| **MCP / HTTP hardening (P2-15, P2-10, P2-11, P2-17)** | `turn` parses via `_safe_int` (no ValueError leak on `"abc"`); autoreflection/archive error responses return generic `detail` (paths/SQL no longer leaked); CORS allows DELETE; `main.py` call-agent cache is bounded at 8 with graceful shutdown eviction |
| **Cache invalidation on reload (P2-12)** | `refresh_config` clears `research_agent._domain_cache` alongside the other derived caches |

**Migration:** none — no new tables or columns. Behavior notes: (1) Reflection knowledge is now persisted and tenant-scoped; previously-merged in-memory-only insights are not back-filled. (2) Memory-state transitions no longer cross user boundaries. (3) Profile-scoped deletes no longer affect other profiles' reflections. Verified: batched E2E/regression checks per finding — sparse tags, profile deletes, TTL cascades, in-memory delete, cross-user state scan, restart persistence, half-write rollback, RL bucket swap, bundled-YAML loading, config fallback semantics, HTTP error opacity.

---

## v1.2.15 — Deep-Audit Fixes: Dead-Path Reactivation, Tenant Scoping & MCP Isolation (2026-09-21)

External deep-audit round: four high-severity findings had left three advertised capabilities (auto-reflection, the lifecycle state machine, knowledge evolution detection) as dead code on the main paths — every finding was reproduced, fixed, and covered by regression/integration checks. Plus unified default-user identity and MCP client isolation.

| Area | Change |
|------|--------|
| **Auto-reflection dead path** | `_trigger_auto_reflection._run` assigned to the closure's own `batch_size` on the RHS — an `UnboundLocalError` on EVERY auto-reflection, silently swallowed by the except → renamed to a distinct local (`bs`); every scheduled reflection now actually runs |
| **Lifecycle state machine dead path** | The state scan's SELECT referenced `last_updated`, a column that exists only on `user_memory` — `no such column` on the first table killed the whole scan in debug silence (zero Active→Stale→Archived transitions ever) → column dropped (`_freshness` already falls back `last_access_at` → `created_at`) and the scan-failure path is now a warning, not debug |
| **Knowledge evolution dead path** | `_detect_knowledge_evolution` ran AFTER the new entry was saved + mirrored, so the new entry itself was always in the candidate set with Jaccard 1.0 and the post-loop self-reference check (`best_id == knowledge_id`) made detection a deterministic no-op → the self entry is excluded inside the candidate loop |
| **Evolution provenance** | `store()` / `POST /api/memory/store` / MCP `echomind_store` accept a `turn` index, threaded through to the evolution rows (`origin_turn` — previously always 0) |
| **GSPO opt-in (behavior change)** | Cluster aggregation overwrote the five-factor RL scores with one geometric mean per cluster and defaulted ON → now opt-in (`rl.gspo.enabled`, default **false**), and an empty `session_id` no longer merges every same-source record into one cluster |
| **Tenant-scoped knowledge ids** | `kb_id` was a bare content md5 — user B's identical insert UPDATEd over user A's row (`user_id=excluded.user_id`) → the hash now carries the tenant (`user_id \x00 content`), and the in-memory content-hash dedup (`knowledge_agent.add_document`, reload index) is scoped the same way |
| **MCP identity isolation** | The HTTP `/mcp` endpoint serves many clients from ONE process, so the single module-global client identity let client B's calls be attributed to whichever client initialized last → HTTP connections key the captured identity by `Mcp-Session-Id` (or `X-Session-Id`), with `X-Client-Name` as a per-request override; the stdio gateway keeps the module global (one process per connection) |
| **Hot-path LLM gate** | `_detect_research_domain`'s sync LLM fallback sat on the retrieve path — 60s timeout × 3 attempts ≈ 181s worst case per retrieval → opt-in via `retrieval.llm_domain_detect` (default **false**; keyword match + "general" fallback remain) and hard-bounded to 5s per call |
| **MCP endpoint auth** | `POST/GET /mcp` were the only unauthenticated routes on a full-memory read/write surface → they now require the same `X-API-Key` as `/api/*` (still open when no key is configured, matching `verify_api_key`); the stdio→HTTP bridge already sends the key |
| **Unified default_user identity** | Entrypoints that do not receive an explicit `user_id` now scope memories to the configured top-level `default_user` (open-source default `"default"`) instead of per-session ids or the shared `"cli"`: `mcp_common._default_user_id()` replaces six `"cli"`/`""` fallbacks, `hermes_provider` stops fragmenting one user's memory across per-session identities (10 such identities observed in a live DB), and `main.py` routes eight fallbacks through the same helper. `clientInfo` inference stays provenance-only (`origin_client`); identity and origin remain separate dimensions |

**Migration:** none — no new tables or columns. Behavior notes: (1) `rl.gspo.enabled` defaults to false; set it true to restore cluster aggregation. (2) `retrieval.llm_domain_detect` defaults to false; set it true to re-enable the LLM semantic domain fallback. (3) Existing `k:` knowledge ids are NOT re-keyed — new-id inserts create one-time duplicates for previously-collided rows, cleanable manually. (4) MCP clients talking to a key-configured server must send `X-API-Key` on `/mcp` (stdio gateways need no change). Verified: 74 regression tests + targeted integration checks (state transitions, evolution rows with `origin_turn`, cross-user dedup, per-session MCP identity).

---

## v1.2.14 — Source Provenance: Origin Tracking, Tag Filters & Structured Query (2026-09-19)

Every memory record now carries a self-describing source envelope — **transport** (mcp/http/hermes/cli) + **origin client** (claude-code/opencode/...) + project + tags + captured time — and can be retrieved by any combination of those predicates, from any supported entrypoint.

| Area | Change |
|------|--------|
| **Tag provenance** | `echomind_store` / `store()` accept caller `tags` (priority); auto topic tags fill the remainder (case-preserving, casefold-deduped, ≤12 tags, ≤32 chars). `echomind_retrieve` / `retrieve_for_task` accept `tags` + `tags_match_all` (OR default, AND opt-in) — the agent-level tag filters existed but were never invoked before |
| **Origin columns** | Migration v10 adds `origin_platform` (transport) and `origin_client` (producing client) to knowledge/experience/task/research/transcript (+ `origin_client` on context/reflections, whose legacy `platform` column is kept and dual-written) with composite indexes; empty defaults keep legacy rows visible to any origin filter |
| **MCP client inference** | The `initialize` handshake's `clientInfo.name` is captured (normalized) as the connection's `origin_client` — a store from Claude Code is recorded as `mcp`/`claude-code` with no caller effort; explicit arguments override |
| **Cross-origin soft penalty** | Records whose origin differs from the querying transport are down-weighted ×0.5 (config `retrieval.origin_cross_soft_enabled` / `origin_cross_soft_penalty`, switchable); legacy rows without an origin are never penalized |
| **Provenance envelope** | `store()` snapshots a full envelope (`schema: envelope-v1`) into task/knowledge/experience metadata; `envelope_from_record` rebuilds a fallback from flat origin fields so pre-envelope records still render |
| **Visible sources** | The markdown archive gains an Origin column per knowledge/experience/task row — `[2026-09-19][mcp/claude-code][projA][代码习惯,coding]` — and MCP `echomind_retrieve` output shows `origin=` per entry |
| **echomind_query** | New structured provenance query (MCP tool + `POST /api/memory/query` + `query_memory` skill + CLI `query` subcommand): exact predicates on project / tags (OR/AND) / origin_client / origin_platform / date range (inclusive; one day = `date_from=date_to`) / memory type, no relevance scoring, merged across 7 memory tables |
| **Robustness** | Every new filter is a bound parameter (no SQL string interpolation); unknown `memory_type` values raise ValueError → HTTP 400; tables without origin columns are skipped, not fatal |

**Migration:** v10 runs automatically on first connect (idempotent `ADD COLUMN` + `CREATE INDEX`, BUSY-retried). No data changes; legacy rows keep their current recall. Ranking note: the cross-origin soft penalty changes ordering when querying across transports — disable via `origin_cross_soft_enabled: false` to restore.

---

## v1.2.13 — Deep-Review Hardening: Isolation, Concurrency & Scoring Consistency (2026-09-13)

Deep code-review hardening across three phases — tenant isolation, RL/transactional concurrency, and unified retrieval/scoring semantics — with behavioral changes to ranking noted below.

| Area | Change |
|------|--------|
| **Tenant isolation** | Knowledge dedup (`search_knowledge_by_content`) is scoped by `user_id`/`profile` — one user's dedup can no longer key off (or silently skip because of) another user's row; `record_feedback` passes `profile` through the Hermes `call()` path (previously crossed into the `default` profile's RL weights) |
| **Delete cascade & profile safety** | `delete_user_memories` no longer deletes `session_transcripts` across profiles (only `reflections` lacks a profile column); single-record and user-wide deletes now cascade to `memory_states`, `knowledge_evolution`, `hit_history`, `reflection_daily_count` (orphan rows and inflated health stats eliminated) |
| **RL read concurrency** | `load_weights_for_user` returns the effective weight snapshot and scoring uses exactly that snapshot; `get_current_weights` is serialized — the load-then-read window that let one user score with another's weights is closed |
| **Transactional IO** | LLM entity extraction moved out of the `store()` write transaction — the `BEGIN IMMEDIATE` lock is never held across network IO (previously an LLM timeout blocked every writer and rolled back the whole memory batch) |
| **Reflection quota atomicity** | Reserve-then-refund: the daily limit is enforced by a single atomic conditional upsert (cross-process TOCTOU closed); failed reflections (parse error / low confidence) refund their slot and never consume quota |
| **Unified scoring (behavior change)** | New `_score_base` normalizes weighted signals per source: freshness is the single recency lever (knowledge no longer double-decays), the domain boost is multiplicative, and `trust_score` now drives experience ranking (the fixed `recency_multiplier` constant is removed) |
| **Retrieval consistency** | `max_results` is honored inside `retrieve_for_task` (previously core always capped at 8, so HTTP `max_results>8` was silently ignored); platform defaults are explicit per entrypoint (`http`/`hermes`/`mcp`); the in-memory context uses the same key as the DB row |
| **Diversity selection** | `_diversify_top_k` is two-pass bucketed: each domain gets one guaranteed representative (previously a dense single domain could occupy every slot) |
| **Config validation** | Validation never deletes user YAML values (rejected keys fall back at read time); list/tuple elements are range-checked (a negative `max_daily` list previously disabled reflection silently); config hot-reload clears all derived caches and hot-refreshes the daily limit; per-path `get_config_manager` instances are cached |
| **Security** | `/api/config/parameter` enforces a section whitelist and protects `api_key` from runtime overwrite; unknown memory types return 400 (not 500); MCP notifications return an empty 202 body |
| **Lifecycle & observability** | Pending reflections are flushed and the reflection thread joined before `call()`-agent teardown and cleared on session reset; data-loss and LLM-config-sync failures log warnings instead of debug-silent |
| **Robustness & tests** | Fallback engine normalizes list-shaped LLM fields (valid-but-misshaped responses are no longer discarded); chunking enforces a hard upper bound on over-long single lines; CLI gains action whitelist, stdin schema validation and try/finally cleanup; `tests/test_api.py` runs on a temp DB (previously touched the real `~/.echomind/memory.db`); dead code removed (`_pending_reflection_event`, `old_cols`, duplicate chunking branch) |

**Note (behavior change):** ranking order changes with the unified scoring — knowledge ages at the documented half-life speed (previously quadratic), experience recency is now time-based, and `trust_score` participates in experience ranking. Existing RL weights remain valid; recalibrate after observing retrieval quality for 1–2 weeks. `retrieval.recency_multiplier` is deprecated (commented in the config templates; uncommenting has no effect).

**No migration required:** no new tables or columns; all changes are in-place code and config-comment updates.

---

## v1.2.12 — Algorithm Improvement: Core-Term Novelty, RL Verification & Chunking (2026-08-26)

Algorithms improvement — core-term novelty ratio, candidate significance verification, and code-block-safe chunking — into EchoMind's LLM + RL architecture as zero-LLM fast heuristics on the hot path.

| Area | Change |
|------|--------|
| **Core-term novelty ratio** | `_core_term_novelty` / `_known_core_terms` extract 3-4 char CJK core n-grams and gate `_detect_knowledge_evolution`: a sentence that mostly overlaps an old one but carries a brand-new concept (novelty ≥ 0.85) is no longer downgraded to `replaces`/`enriches` via the sentence-level Jaccard |
| **Known-term corpus** | built from the in-memory `knowledge_agent.store` first, with a SQL DB fallback (`get_knowledge_content`) when the store is below `_MIN_TERM_STORE_SIZE` (cold start / eviction), plus cache invalidation on write/evict — replacing AEIS's incomplete `query_nodes(limit=80)` sampling |
| **RL significance verification** | `verify_improvement(hits_bool, baseline_bool)` uses binomial standard error (success > baseline + 2·SE); `hit_history` SQLite table persists binary hits (fixing AEIS's non-persistent equivalent); `record_feedback` logs hits and runs verification every 50 feedbacks with a conservative failure ladder (halve LR on first miss) |
| **Code-block-safe chunking** | `chunk_text()` (core/chunking.py) extracts fenced code blocks whole, never splitting on inner blank lines, slicing over-long blocks in line groups; `add_research_note` keeps the 2000-char cap and chunks with `chunk:i` tracing tags |

**Note:** `hit_history` is a new table; no migration impacting existing data. The novelty gate is a soft signal and does not replace the LLM relation classifier.

---

## v1.2.11 — Project Scoping & Hermes Persona Fix (2026-08-24)

Fixes cross-agent memory contamination for the MCP (DSH/Zcode) and Hermes paths by making `project` a live scoping key and restoring Hermes profile (persona) isolation.

| Area | Change |
|------|--------|
| **Project scoping** | `default_project` top-level config key now consumed at runtime (`ConfigManager.get_top_level`) and used by the MCP gateway to resolve the project when a client omits it — no longer a dead config key, and MCP traffic stops landing in the shared `"default"` namespace silently |
| **Hermes persona isolation** | `initialize()` prefers the host-supplied `agent_identity` (the active Hermes profile/persona name) as the memory `profile`; `_derive_profile(hermes_home)` is now only a fallback, and `project` is no longer hardcoded to `"hermes"` |
| **Diagnostics** | `retrieve_for_task`/`store` emit a warning when `project` is still `"default"` so unscoped writes are observable |
| **Knowledge dedup** | knowledge primary key changed from task-scoped to content-scoped (`k:<content_hash>`), so `ON CONFLICT(id)` actually fires — fixing unbounded knowledge_memory growth and broken dedup |
| **Preferences double-nesting** | `store()` persists the raw nested preferences instead of the flat `get(platform=)` expansion; `_merge_platform_prefs` adopts already-nested input wholesale, preventing `_default` pollution and double-nesting |
| **Feedback profile passthrough** | `/api/memory/feedback` (HTTP and MCP) now passes `profile` through so RL weights are isolated per profile, closing the persona-level RL leak |
| **Keyword entity fallback** | FALLBACK_CONFIG adds an `entities.technologies` section so keyword entity extraction has a source when no LLM is available (previously always empty) |

**Note:** `platform` remains a soft-weight (same-platform ×1.0, cross-platform ×0.5) for the context source; knowledge/experience/task scoping is by `user_id + project + profile`. No schema migration in this release.

> Known low-impact issues intentionally not fixed (deferred for a focused refactor): `session_id` is semantically split between context (stable key) and task/experience (raw id) but this does not affect retrieval; `sync_to_code_project` export is not filtered by project.

---

## v1.2.10 — Algorithm Optimization Pass (2026-08-15)

Algorithmic pass closing the reflection loop and hardening the RL learning path with per-user isolation.

| Area | Change |
|------|--------|
| **Reflection loop** | `_reflective_fallback.py` implements the 4 `_merge_*`/`_save_reflection` stubs + consumes `_process_reflection` output (P1-A); adds the positive `_reinforce_weights` arm symmetric to `decay_all`, plus a few-shot prompt-build bug fix (P1-B) |
| **RL credit assignment** | `_update_weights` credits only dimensions whose mapped sources actually appeared in the feedback (P2-B) — previously softmax + M-4 neutral fallback diluted every positive feedback and no dimension's share ever rose |
| **Normalization invariants** | Declared `_WEIGHT_INVARIANT_UPDATE/DECAY = "linear"` + wired periodic anti-divergence `decay_all` into `_update_weights` (P3-A); `decay_all` normalize-then-clamp order fixed (range invariant) |
| **Daily limit per-user + durable** | Daily reflection limit is now per `(user_id, date)` and persisted to SQLite (`reflection_daily_count`), surviving restarts (P5-B) |
| **RL meta-state per-user** | LR/exploration schedule, history, divergence snapshots, cumulative counters keyed per user — one user's feedback no longer advances another's trajectory (P5-A) |
| **Storage indexes** | Added idempotent join/lookup indexes (knowledge content, task/experience by user+created, reflections by user+created) (P6-A) |

**Tests:** 102 passed (including new daily-limit, meta-state isolation, reflection-loop, RL projection, stable-ID, storage, and freshness regression tests).

**Follow-up audit round (post-release fixes):**
- **HIGH-1**: `/api/reflect` passes `user_id` to `_check_daily_limit`, so hitting the daily limit returns 429 instead of a TypeError-500 (restores the limit/parse-failure status distinction).
- **Daily-limit authority (MED-2)**: on every read the count is re-read from the store (not seeded once per instance), so HTTP + Hermes sharing one DB no longer each run their counter to the limit (2×..N× overshoot). Regression test for cross-instance visibility.
- **RL empty-credit no-op (MED-3)**: a feedback with empty `retrieved_memories` (empty `present_set`) credits no dimension and no longer advances the exploration schedule it never earned.
- **RL threading (MED-5)**: load/decay/flush serialize on a per-optimizer lock.
- **Single-writer reflection persist (MED-6)**: removed the duplicate `_run` `auto:` save; the fallback `_process_reflection` is the single writer, symmetric with the native engine.
- **Reflection id uniqueness (MED-7)**: id now uses `time.time_ns()` — no same-second PK collide/overwrite.
- **Mixed-language tokenization (MED-8)**: CJK bigrams are extracted regardless of overall language detection, so mixed zh/en strings (and kana/hangul) no longer drop all hanzi from the Jaccard used for knowledge evolution.
- **Experience relevance vs frequency (MED-9)**: `find_similar_tasks` relevance is now query-token coverage, not a disguised frequency function — frequency is no longer double-counted.
- **Preference platform passthrough (MED-10)**: reflection-derived preferences land in the platform-specific bucket, not only `_default`.
- **Low-confidence discard (P1-A #9)**: below-threshold fallback reflection returns `None` (neither persists nor consumes quota), matching the native engine.
- **Polish**: prune stale daily-count cache keys (#7); drop the redundant `task_memory(user_id)` index (#10); hoist module-level imports (O1); fold dead `_compute_rcw_advantages` wrapper + correct clamp/decay comments (F8/F4/F5).

---
## v1.2.9 — Markdown Rendering & Hermes v0.20 Adaptation (2026-08-12)

| Feature | Description |
|---------|-------------|
| **Markdown Memory Archive** | `export_memory_to_markdown()` produces complete .md (9 sections); `core/markdown_renderer.py` zero new deps |
| **Compact Inject Layer** | `_format_prefetch_context` now emits `<memory-context>` blocks (Hermes v0.20 compatible) |
| **Hermes v0.20 Adaptation** | Root `__init__.py` `register(ctx)` + `plugin.yaml` `kind: exclusive` |
| **Cognitive Position Implementation** | cognitive_pos (nok/fok/exo) full lifecycle |
| **HTTP Endpoint** | `GET /api/memory/archive` |
| **Bug Fixes** | register placement (BUG-1), dead test (BUG-2), search_all dead code (BUG-3) |

**Tests:** 62 passed.

---
## v1.2.8 — Self-Reflection Absorption Phase 1+2 (2026-08-11)

| Feature | Description |
|---------|-------------|
| **Epistemic Mode** | knowledge entries now carry `epistemic_mode` in metadata (user_provided / reasoned / fuzzy / referenced), resolved from source at write time — zero LLM cost |
| **Provenance columns** | Migration v9 adds `origin_agent`, `origin_session_id`, `origin_turn` to `knowledge_evolution` for memory-supply-chain tracking |
| **Self-Reflection Score** | `compute_autoreflection_score()` evaluates 4-criterion maturity: situated-awareness, architectural-congruence, analysis-from-architecture, incorporation — returns (score 0-4, diagnostic summary) |
| **System Prompt Diagnostics** | `system_prompt_block()` now appends real-time memory health (stats, RL weights, evolution status) to the agent's context |
| **Knowledge Search** | search results include `epistemic_mode` and `epistemic_detail` for downstream trust evaluation |
| **Cognitive Position** | knowledge entries track `cognitive_pos` (nok/fok/exo) in metadata — contextual proximity supplementing Ebbinghaus |

**Tests:** Added 8 regression tests (epistemic resolver, provenance migration columns, autoreflection scoring, knowledge search); full suite 56 passed.

---
## v1.2.7 — Deep Code Review Fixes & Regression Tests (2026-08-04)

**Review method:** full deepseek-v4-flash code review + 4-parallel agent audit of memory data-links, then fix + 48-test suite (33 existing + 15 new).

| Area | Fixes |
|------|-------|
| **Data-link / Freshness** | `_load_from_db` restores all timestamps (Ebbinghaus survives restart); unified `last_access_at` format; knowledge `last_access_at` propagated; user `model_dump(mode=json)`; `_freshness` handles datetime objects |
| **Transaction** | `_batch_active` + `_maybe_commit()` gating → `transaction()` now truly atomic (rollback on failure) |
| **Persistence** | Completed UPSERT `DO UPDATE SET` for task/experience/knowledge/paper/note; migration v3 preserves `created_at` |
| **Dispatch/API** | `main.py` forwards `project`/`session_id`/`title`/`correction`; `api_delete_user` → HTTP 500; `mcp_gateway` thin wrapper (version 1.2.7); reflect profile scoping |
| **RL/Safety** | daily-limit resets across UTC days; `db._lock` on state writes; single freshness; `_content_index` rebuild on load; safe JSON loads; transcript upsert; `batch_score` parse |
| **Critical bug** | `models/context.py` missing `Optional` import (fixed) |

**Tests:** fixed conftest + storage/core assertions; added `tests/test_regressions.py` (15 tests).

---
## v1.2.6 — Bug Fix & Reliability Release (2026-07-31)

**Fixes: 42 issues across 3 audit rounds covering core engine, storage layer, and API layer.**

| Category | Fixes | Key Changes |
|----------|:---:|-------------|
| **Critical** | 8 | Hermes LLM sync dead code restored, sync_turn crash fix, /api/reflect exception handling, HTTP params gaps filled |
| **High** | 13 | knowledge/experience last_access_at update fix, RL decay_all redesign, predict_score semantic fix, config priority corrected |
| **Medium** | 13 | context LRU order fix, memory state decay for context, HTTP 500 error codes, LLM retry with exponential backoff |
| **Low** | 8 | Config validation, per-user RL weight isolation, code dedup in MCP gateway, return type unification |

**Architecture Changes:**
- `mcp_gateway.py` refactored from 372-line duplicate to 80-line thin wrapper delegating to `mcp_common.py`
- `StoreRequest` and `ReflectRequest` now include `project`/`session_id`/`correction`/`profile` fields
- MCP tools now pass `project`/`session_id`/`profile` parameters
- `ExperienceEntry` model now includes `last_access_at` field
- `ContextMessage.content` now accepts None (tool-call message compatibility)
- Config validation added for critical parameters
- Migration v4 indexes expanded to include `context_memory` and `research_papers`

**API Changes:**
| Endpoint | Change |
|----------|--------|
| `POST /api/memory/store` | New params: `project`, `session_id`, `correction` |
| `POST /api/memory/retrieve` | New params: `project`, `session_id` |
| `POST /api/reflect` | New param: `profile` |
| MCP `echomind_reflect` | Added Phase 2 support (`llm_response` param) |
| MCP `echomind_retrieve`/`echomind_store` | Added `project`/`session_id`/`profile` params |

---

**Core Highlights:**
*RL advantage baseline, RCW per-source weighting, knowledge diversity, profile export.*

| Feature | Description |
|------|------|
| **RL Advantage Baseline** | Linear-recency weighted history baseline replaces raw reward — more stable weight updates |
| **RCW Per-Source Weighting** | Relevance × trust scores mapped to weight dimensions — fairer per-source reward contribution |
| **KPop-Aware Decay** | KL-divergence-triggered extra weight decay when policy diverges from snapshots |
| **Knowledge Diversity** | Domain-aware top-K retrieval ensures retrieval results span multiple knowledge domains |
| **Profile Export** | Human-readable `profile.md` with preferences, knowledge, experience, papers, hot domains |
| **Hot Domain Tracking** | Tag and domain statistics surfaced in behavior hints for agent awareness |


---
## v1.2.2 New Features

**Core Highlights:**
*Memory lifecycle management, knowledge evolution tracking, entity extraction, Streamable HTTP MCP.*

| Feature | Description |
|------|------|
| **Memory State Machine** | Active → Stale → Archived → Superseded lifecycle tracking, automatic state transitions via Ebbinghaus freshness |
| **Knowledge Evolution** | Jaccard + LLM hybrid detection (Replaces/Enriches/Confirms/Challenges) |
| **Memory Health Report** | Health summary section in output |
| **Flags System** | Automatic needs_verification and contradiction detection for knowledge entries |
| **Entity Extraction** | LLM-first keyword-fallback (technologies/concepts) |
| **Streamable HTTP MCP** | `POST /mcp` + `GET /mcp` — EchoMind MCP now accessible remotely via JSON-RPC over HTTP |
| **Shared MCP Tool Layer** | Single source of truth for MCP tools shared across stdio and HTTP transports |


---
## v1.2.0 New Features

**Core Highlights:**
*MCP stdio gateway for Claude Code, Ebbinghaus forgetting curve, session-isolated context, memory CRUD.*

| Feature | Description |
|------|------|
| **MCP stdio Gateway** | 7 native Claude Code tools (retrieve/store/search/feedback/reflect/delete/health) via stdio JSON-RPC |
| **Ebbinghaus Forgetting Curve** | Freshness-based memory scoring across all 6 memory types, auto-excludes stale records |
| **Memory Delete API** | DELETE endpoints for individual records, full user data, and TTL-based cleanup |
| **Session-Isolated Context** | Each session_id gets an independent context window with LRU eviction (up to 5 active sessions) |
| **Session Message Archive** | Evicted session messages preserved in data table |
| **User Correction Detection** | zh/en keyword matching for correction signals triggers immediate reflection |
| **6-Category Preference Inference** | code_style, response_style, platform, language, depth, tone — keyword-driven from config |
| **Adaptive Reflection Batch** |  based on weekly user activity |
| **RL Cosine Decay + Epsilon-Greedy** | Cosine learning rate decay prevents late-stage weight oscillations; epsilon-greedy exploration escapes local optima |
| **SQLite Schema Migrations** | Structured  list with transactional rollback — replaces ad-hoc ALTER TABLE |
| **Atomic Batch Writes** |  wraps 5 save calls in a single  transaction |
| **Hermes Agent v0.17.0** | Full MemoryProvider compatibility including `get_config_schema()`, `backup_paths()`, and `save_config()` |


---
## v1.1.0 New Features

**Core Highlights:**
*Introducing a **dedicated Reflection Engine Agent** that proactively distills semantic memory and procedural memory from raw episodic memory. Analogous to human "bedtime reflection" or the Reflexion/SRMA architecture.*

| Feature | Description |
|------|------|
| **Self-Evolving Engine Agent** 🧠 | Automatically extracts long-term knowledge from raw conversations. Auto-triggers **self-reflection** to distill raw interaction records into persistent knowledge, user preferences, and procedural rules — achieving true memory self-evolution |
| **Upgraded RL Capabilities** | RL weight range mode, random sampling, automatic convergence from user feedback |
| **Configurable Domain Prompts** | Domain prompts are now configuration-driven — no code changes needed for tuning |
| **Confidence Filtering** | Reflection results below the confidence threshold are automatically discarded, **preventing hallucination pollution of memory** |
| **Memory Source Tracking** | Complete storage of reflection records with platform tags and source traceability |
| **Importance Scoring** | Scores memory importance, preserving valuable memories |
| **Multi-Trigger Retrieval** | Keywords + RL weights + LLM semantics — a true "semantic memory system" |
| **Memory Isolation** | Isolation by user, project, session, topic, and research domain — no more memory chaos |
| **Architecture Upgrade** | New reflection engine architecture supporting highly flexible prompt configuration |


---

## Academic References by Version

The technical design of the Self-Reflective Agent component in the v1.1.0 release is inspired by the following research:

### 1. SAGE: Self-evolving Agents with Reflective and Memory-Augmented Abilities

Liang, X., He, Y., Xia, Y., Song, X., Wang, J., Tao, M., Sun, L., Yuan, X., Su, J., Li, K., Chen, J., Yang, J., Chen, S., & Shi, T. (2024).

- **Paper:** [arXiv:2409.00872](https://arxiv.org/abs/2409.00872)
- **Journal:** *Neurocomputing* (2025)
- **Release Version:** Echomind Memory Engine v1.1.0


### 2. SRMA: Self-Reflective Memory Consolidation in Agentic Architectures

Satya, P. R. B. (2026).

- **Paper:** [IJCA Vol.187 No.73](https://www.ijcaonline.org/archives/volume187/number73/self-reflective-memory-consolidation-in-agentic-architectures/)
- **Journal:** *International Journal of Computer Applications*, 187(73)
- **Release Version:** Echomind Memory Engine v1.1.0


### 3. Lewis (2026) "Autoreflection: How Agentic Strange Loops Turn Human Culture into AI Infrastructure"

- **Paper:** https://arxiv.org/abs/2608.03800
- **Release Version:** Echomind Memory Engine v1.2.8
- **Scope:** epistemic knowledge classification, provenance tracking, architectural self-diagnosis, self-reflection scoring

---

## Acknowledgments

We sincerely thank the authors of the above papers for their pioneering work on self-reflective memory mechanisms. Their research has provided valuable theoretical foundations and inspiration for the design of EchoMind-Memory.skill's Self-Reflective Agent.

The technical design of this project's Self-Reflective Agent benefits from the inspiration of the above groundbreaking research. We extend our sincere academic gratitude to the paper authors.

At the same time, EchoMind-Memory.skill's "self-evolution" primarily differs from the above scientific research in its adoption of **dependency inversion** (core engine with zero LLM coupling), **platform-aware isolation**, and **zero-configuration deployment** — making it directly usable in production Multi-Agent systems without additional infrastructure. This is a production-grade agent application.



---

## Historical Version Notes


### v1.0.10 — Full Hermes v0.14.0 Compatibility (2026-05-17)

**Added (MemoryProvider ABC compatibility):**

| Method | Description |
|------|------|
| `queue_prefetch()` | Compatible with the new Hermes v0.13.0+ interface, eliminating per-turn AttributeError logs (was previously causing error logs on every turn) |
| `on_session_switch()` | Fixes session ID corruption after `/resume` `/branch` `/reset` operations (fixes session ID corruption after session switch operations) |
| `on_pre_compress()` | Auto-saves memories about to be discarded before context compression (auto-saves memories before context compression discards them) |
| `on_delegation()` | Captures sub-agent task experience into long-term memory (captures sub-agent task experience into long-term memory) |



### v1.0.9 — OpenClaw / OpenCode / Claude Code Three-Platform Compatibility Fix (2026-05-16)

| Fix | Affected Platforms |
|--------|---------|
| `main.py` added `call()` dispatch function | OpenClaw |
| `http_api.py` retrieve/store endpoints pass through `platform` parameter | All platforms |
| `code_format/cli.py` fixed async→sync crash | OpenCode |
| `skill.yaml` added `platform` parameter + `openclaw.call` declaration | OpenClaw |

### v1.0.8 — Platform-Aware Memory + Hermes Adapter (2026-05-15)

- Platform-aware memory: same-platform weight ×1.0, cross-platform ×0.5
- Hermes Agent plugin: implements MemoryProvider interface, auto-save/load each turn
- WAL concurrency mode + automatic data migration


## v1.0.8 Existing Features

| Feature | Description |
|------|------|
| **Hermes Adapter Plugin** | Implements Hermes Agent memory interface for auto-save/load each turn. Code-driven, no LLM decisions needed, 100% reliable |
| **Platform-Aware Memory** | All context memory tagged with platform labels (hermes/openclaw/opencode); same-platform weight ×1.0, cross-platform ×0.5; user preferences isolated by platform |
| **WAL Concurrency Mode** | Supports multi-process concurrent read/write |
| **Auto-Migration** | Old table structures auto-migrated on upgrade |
| **User Preferences Isolated by Platform** | Different users, different apps, different platforms have independent preferences — keep your memories isolated |







---
