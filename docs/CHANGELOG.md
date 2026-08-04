# EchoMind Changelog

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

## v1.1.0 Academic References

The technical design of the Self-Reflective Agent component in this v1.1.0 release is inspired by the following research:

### 1. SAGE: Self-evolving Agents with Reflective and Memory-Augmented Abilities

Liang, X., He, Y., Xia, Y., Song, X., Wang, J., Tao, M., Sun, L., Yuan, X., Su, J., Li, K., Chen, J., Yang, J., Chen, S., & Shi, T. (2024).

- **Paper:** [arXiv:2409.00872](https://arxiv.org/abs/2409.00872)
- **Journal:** *Neurocomputing* (2025)


### 2. SRMA: Self-Reflective Memory Consolidation in Agentic Architectures

Satya, P. R. B. (2026).

- **Paper:** [IJCA Vol.187 No.73](https://www.ijcaonline.org/archives/volume187/number73/self-reflective-memory-consolidation-in-agentic-architectures/)
- **Journal:** *International Journal of Computer Applications*, 187(73)

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
