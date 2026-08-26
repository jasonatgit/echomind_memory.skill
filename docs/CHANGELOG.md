# EchoMind Changelog

## v1.2.12 — Algorithm Improvement: Core-Term Novelty, RL Verification & Chunking (2026-08-26)

Absorbs three dsh-memory (AEIS) algorithms — core-term novelty ratio, candidate significance verification, and code-block-safe chunking — into EchoMind's LLM + RL architecture as zero-LLM fast heuristics on the hot path.

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
