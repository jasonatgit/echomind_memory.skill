<p align="center">
  <img src="assets/banner.jpg" alt="echomind_memory.skill" width="100%">
</p>

[![OpenClaw Compatible](https://img.shields.io/badge/OpenClaw-Compatible-brightgreen)](https://github.com/OpenClaw)
[![Hermes-Agent Ready](https://img.shields.io/badge/Hermes--Agent-Ready-blue)](https://github.com/Hermes-Agent)
[![Claude Code Supported](https://img.shields.io/badge/Claude%20Code-Supported-orange)](https://claude.ai/code)
[![OpenCode Compatible](https://img.shields.io/badge/OpenCode-Compatible-red)](https://github.com/open-code-ai)
[![DeepSeek Harness](https://img.shields.io/badge/DSH-dsh--plugin-blueviolet)](https://github.com/deepseek-ai/deepseek-harness)


# EchoMind Memory Engine —— Give Your AI Permanent Memory and Self-Evolution Capabilities


🌐 **中文版:** [README.zh-CN.md](README.zh-CN.md)


> A long-term memory engine supporting the Hermes Agent, OpenClaw, OpenCode, DeepSeek Haeness(DSH) and Claude Code agents.

> Stop your AI from "forgetting" — remember your preferences, style, research methods; self-reflect and self-evolve.

> EchoMind Memory Engine helps you: extract knowledge from conversations, crystallize rules through reflection.


📦 **Repository:** https://github.com/jasonatgit/echomind_memory.skill



---

## 🧠 EchoMind's Core Capabilities

### Core Architecture
| Capability | Description |
|------|------|
| **Seven Types of Memory** | User / Task / Experience / Context / Knowledge / Research / Reflection |
| **Zero-Dependency Local Storage** | SQLite single-file database, no Docker / PostgreSQL / Redis required |
| **SQLite Schema Migration + Transactional Writes** | Structured migration list with transactional rollback; store() wraps 5 save calls in one transaction |

### Memory Intelligence (Reflective Reasoning)
| Capability | Description |
|------|------|
| **Self-Evolving Engine Agent** | Auto-distills semantic knowledge and procedural rules from raw memories with zero-config LLM injection; low-confidence reflections discarded to prevent hallucination pollution |
| **Ebbinghaus Forgetting Curve** | Covers all 6 memory types, auto-downranks or excludes stale records |
| **Memory Lifecycle State Machine** | Active → Stale → Archived → Superseded lifecycle tracking, automatic state transitions via freshness |
| **Knowledge Evolution Tracking** | Replaces/Enriches/Confirms/Challenges relations — Jaccard + LLM hybrid detection |
| **Flags System** | Automatic detection of needs_verification and contradiction in knowledge entries |
| **Memory Health Report** | Aggregated stats by type and state + 7-day growth + flags summary |
| **Entity Extraction** | LLM-first keyword-fallback extraction (technologies / concepts) |
| **Experience Distillation & Reuse** | Previously fixed bugs / used models → auto-recommended next time |
| **Epistemic Knowledge Classification** | Every knowledge entry carries an epistemic_mode (user_provided / reasoned / fuzzy / referenced) — distinguishes real user facts from LLM-generated inference, resolved automatically at write time (zero LLM cost) |
| **Self-Reflection Score & Diagnostics** | Self-assessment via 4-criterion maturity model (situated-awareness, architectural-congruence, analysis-from-architecture, incorporation-and-expansion); real-time system health injected into agent context |
| **Knowledge Provenance Tracking** | Provenance chain (origin_agent, origin_session_id, origin_turn) stored in knowledge_evolution for memory-supply-chain auditing |
| **Markdown Memory Dossier** | `export_memory_to_markdown()` generates a complete 9-section .md document (health / profile / knowledge partitioned by epistemic mode / experience / task / context / research / reflection / self-reflection score); zero new dependencies |
| **Compact Injection Layer** | `<memory-context>` compact Markdown block for LLM context injection (Hermes v0.20+ compatible) |
| **Hermes v0.20+ Adaptation** | Root `register(ctx)` entry point + `plugin.yaml` `kind: exclusive` — compatible with Hermes v0.13–v0.20 |

### Retrieval & Optimization (RL-Enhanced Self-Learning)
| Capability | Description |
|------|------|
| **RL-Enhanced Auto-Optimization** | Adjusts memory weights via user feedback with persistence; cosine learning rate decay + epsilon-greedy exploration |
| **Multi-Trigger Retrieval** | Keywords + RL weights + LLM semantics — a true semantic memory system |
| **Adaptive Reflection Batch** | Dynamically adjusts reflection trigger threshold based on weekly user activity |
| **Few-Shot Anchoring** | Rapidly builds memory norms from small samples, improving memory quality |

### User Understanding
| Capability | Description |
|------|------|
| **6-Category Preference Inference** | code_style / response_style / platform / language / depth / tone |
| **User Correction Detection** | zh/en keyword matching for correction signals triggers immediate reflection |
| **Session-Isolated Context** | Per-session independent context window with LRU eviction + message archive |

### Platform & Integration
| Capability | Description |
|------|------|
| **Cross-Framework Compatibility** | LLM-independent, adapters for Hermes / OpenClaw / OpenCode / Claude Code |
| **Platform-Aware Memory Isolation** | Same-platform ×1.0, cross-platform ×0.5; isolation by user/project/session/topic/domain |
| **Dual-Transport MCP Gateway** | stdio + Streamable HTTP; 7 native Claude Code tools |
| **Memory CRUD API** | DELETE individual / full user + TTL-based automatic cleanup |
| **Hermes Agent Deep Integration** | Compatible across MemoryProvider versions, auto-save and auto-retrieve every turn, zero LLM decisions |

---

### Auto-Retrieval Triggers
EchoMind's memory system is optimized specifically for *research-oriented* memory, storing research papers, theoretical models, and research methodologies.

When a query involves the following *domain keywords* or related *semantics*, the system automatically retrieves research memories: Management Science, AI, NLP, Biology, Computer Science, Robotics, Recommendation Systems, Statistics & Decision Science.


*Other disciplines and keywords can all be customized*


---

## 🔌 Supported Frameworks

| Framework | Integration Method | Reliability |
|------|----------|--------|
| **Hermes-Agent** | MemoryProvider Plugin (automatic, v0.13.0–v0.20.0) | ★★★★★ 100% |
| **OpenClaw** | `skill.yaml` + HTTP API tool invocation | ★★★★☆ LLM-decision |
| **OpenCode** | CLI + HTTP API or MCP stdio | ★★★★☆ LLM-decision |
| **Claude Code** | MCP stdio or HTTP API | ★★★★☆ LLM-decision |
| **DeepSeek Haeness(DSH)** | MCP stdio or HTTP API | ★★★★☆ LLM-decision |


---



## 📝 Blog

| Date | Title |
|:-----|:------|
| 2026-08 | 🎯[ EchoMind： 集成 DSH 为长期记忆服务（MCP）— 实施报告](blog/echomind-dsh-mcp-integration-report.md) |
| 2026-08 | 🧠[EchoMind: Markdown Rendering: Turning AI Memory from a "Black Box" into a Readable Document](blog/echomind-markdown-rendering-article-en.md) |
| 2026-08 | 🎯[ 在"模型军备竞赛"的火线上，老梁的DSH 的插件化是一场豪赌还是一次押对？](blog/dsh-evolution-analysis.md) |
| 2026-08 | [EchoMind：Autoreflection-Teaching AI Memory to Think About Itself](blog/echomind-autoreflection-article-en.md) |
| 2026-07 | [Echomind: Self-Reflective Agent Part 1 — Reflection Engine and Memory Lifecycle](blog/echomind-reflective-agent-part1-article-en.md) |
| 2026-07 | [Echomind: Self-Reflective Agent Part 2 — Knowledge Evolution and Memory Governance](blog/echomind-reflective-agent-part2-article-en.md) |
| 2026-06 | [Echomind: RL Self-Learning Memory System](blog/echomind-rl-article-en.md) |
| 2026-05 | [Memory Engine: Why Every AI Agent Needs a Memory System](blog/echomind-agent-memory-article-en.md) |

*Some content includes AI-generated material.*

---

## 📜 Version History

| Version | Highlights |
|:--------|:-----------|
| v1.2.12 | *Core-term novelty ratio, RL significance verification, code-block-safe chunking.* |
| v1.2.11 | *Project scoping, Hermes persona isolation, content-hash knowledge dedup.* |
| v1.2.10 | *Reflection loop closure, real RL credit assignment, per-user meta-state and daily limit, storage indexes.* |
| v1.2.9 | *Markdown memory archive (9-section .md), Hermes v0.20 adaptation, cognitive_pos lifecycle.* |
| v1.2.8 | *Self-reflection absorption : epistemic classification, provenance tracking, architectural self-diagnosis. * |
| v1.2.7 | *Deep code review: 42 bug fixes + 48 regression tests.* |
| v1.2.3 | *RL advantage baseline, RCW per-source weighting, knowledge diversity, profile export.* |
| v1.2.2 | *Memory lifecycle management, knowledge evolution tracking, entity extraction, Streamable HTTP MCP.* |
| v1.2.0 | *MCP stdio gateway, Ebbinghaus forgetting curve, session-isolated context, memory CRUD.* |
| v1.1.0 | *Self-Evolving Engine Agent, RL upgrade, confidence filtering, multi-layer memory isolation.* |
| v1.0.10 | *Hermes v0.14.0 full compatibility.* |
| v1.0.9 | *OpenClaw / OpenCode / Claude Code three-platform compatibility fix.* |
| v1.0.8 | *Platform-aware memory, Hermes adapter plugin, WAL concurrency mode.* |

📖 *READ* Full changelog: [CHANGELOG.md](docs/CHANGELOG.md)


---
## 🔗 Quick Links

| Document | Description |
|:---------|:-----------|
| [Installation Guide](docs/INSTALL.md) | Prerequisites, one-click install, Hermes setup, Python quick start |
| [API Reference](docs/API.md) | All 20+ HTTP endpoints |

Data is stored in a single SQLite file at ~/.echomind/memory.db. Back up by copying the file.



## 🔭 Vision

AI is not a tool, it's a collaborator. Collaborators shouldn't have to "re-meet you" every time.

EchoMind enables your AI to:

- Remember your coding style, preferences, and habits
- Remember the bugs you've fixed and approaches you've tried
- Remember the papers and theoretical models you've researched
- Possess an RL-driven self-optimizing weight system — gets smarter with every interaction
- This is not a plugin, this is an **AI Multi-Agent Memory Neural Network** with *self-reflective memory*.



---
## 📧 Contact
*email：*[jasonyouatgmaildotcom](mailto:jasonyouatgmaildotcom)


---
## ❓ Q&A *Click to expand*

<details>
<summary><b>⚙️ Hermes Agent Profile Isolation & FAQ</b></summary>

### Q: How do I use EchoMind across Hermes Profiles?

EchoMind v1.1.6+ supports Hermes Profile-level memory isolation.

**Install once**:
```bash
./install.sh
```

**Automatic behavior**:
- Default profile → memory stored under `profile='default'`
- Other profiles (e.g. weixin) → symlinks created automatically, memory stored under `profile='weixin'`
- Both profiles' memories live in the same `~/.echomind/memory.db`, completely isolated
- Historical data is automatically assigned to the `default` profile

**Per-project isolation within the same profile**:
```yaml
# hermes config.yaml
memory:
  provider: echomind
  project: echomind  # optional, filters by project within the same profile
```

**Manually linking a new profile** (if the profile was created after installation):
```bash
ln -s ~/.hermes/plugins/echomind ~/.hermes/profiles/<profile-name>/plugins/echomind
```

---

### Q: Does EchoMind support Windows?

Yes. v1.1.6+ has fixed cross-platform path resolution. Windows paths (e.g. `C:\Users\...\profiles\weixin\...`) correctly extract the profile name.
If using WSL, paths follow the Linux convention.

---

### Q: Will multiple profiles conflict when using EchoMind simultaneously?

No. v1.1.6+ uses the following mechanisms to guarantee concurrency safety:
1. **WAL mode**: SQLite write-ahead logging, supports concurrent reads across multiple processes
2. **busy_timeout=5000**: waits up to 5 seconds when encountering a lock
3. **Auto-retry**: exponential backoff retry up to 3 times in edge cases

---

### Q: How do I downgrade to an older version?

> ⚠️ **Important**: When downgrading, older versions' `SELECT` queries lack `WHERE profile = ?` filtering, making all profile data visible to the default profile.

**Safe downgrade steps**:
1. Backup `~/.echomind/memory.db`
2. Clear non-default data:
   ```sql
   DELETE FROM task_memory WHERE profile != 'default';
   DELETE FROM user_memory WHERE profile != 'default';
   ```
3. Then roll back to the older version

**Recommendation**: Keep the new version. Do not downgrade.

---

### Q: Where is data stored? How do I back it up?

All data is stored in a single file `~/.echomind/memory.db`. To back up, simply copy the file:
```bash
cp ~/.echomind/memory.db ~/.echomind/memory.db.backup-$(date +%Y%m%d)
```

---

### Q: Will data be lost after migration?

No. SQLite `ALTER TABLE ADD COLUMN ... DEFAULT 'default'` is an O(1) metadata operation — it does not modify rows row-by-row. Existing 37MB of data is fully preserved, automatically assigned to the `default` profile.

---

### Q: Is EchoMind compatible with Hermes v0.16.0?

Yes. EchoMind v1.1.6+ has been adapted to Hermes v0.16.0's new `on_session_switch(rewound=True)` parameter.
When the user executes `/undo N` to truncate conversation history, EchoMind automatically clears the context cache to prevent memory contamination.

### Q: Is EchoMind compatible with Hermes v0.17.0?

Yes. EchoMind v1.2.0+ fully supports Hermes v0.17.0's MemoryProvider interface, including `get_config_schema()`, `backup_paths()`, and `save_config()` methods. Compatibility range: Hermes v0.13.0 – v0.17.0.

</details>

<details>
<summary><b>🌐 MCP Gateway Setup & FAQ</b></summary>

### Q: How do I connect EchoMind to Claude Code via MCP?

**Local stdio mode** (no HTTP service required):
```bash
claude mcp add echomind -- python ~/.hermes/skills/echomind-memory/adapters/mcp_gateway.py
```

**Remote HTTP mode** (requires `python main.py` running on port 8005):
```json
{
  "mcpServers": {
    "echomind": {
      "url": "http://<your-server>:8005/mcp",
      "type": "streamableHttp"
    }
  }
}
```

> ⚠️ HTTP MCP mode requires the EchoMind HTTP service to be running (`python main.py`). If the service stops, remote MCP connections become unavailable. stdio mode is unaffected.

### Q: What MCP tools are available?

EchoMind exposes 7 MCP tools:

| Tool | Description |
|------|-------------|
| `echomind_retrieve` | Search long-term memory by query |
| `echomind_store` | Persist an interaction into memory |
| `echomind_search` | Search session transcripts |
| `echomind_feedback` | Provide feedback on retrieval results |
| `echomind_reflect` | Trigger reflection on recent memories |
| `echomind_delete` | Delete a specific memory entry |
| `echomind_health` | Check service health and version |

### Q: MCP connection fails — what should I check?

1. **stdio mode**: Verify the gateway path is correct — `python -c "from adapters.mcp_common import handle_mcp_request"` should succeed
2. **HTTP mode**: Confirm `python main.py` is running and `curl http://127.0.0.1:8005/health` returns `"status":"ok"`
3. **Authentication**: If `api_key` is configured in `echomind_config.yaml`, set `ECHOMIND_API_KEY` environment variable for the MCP gateway

### Q: Does MCP work with tools other than Claude Code?

Yes. MCP stdio is compatible with any MCP host (Claude Desktop, Cursor, Cline, etc.). Remote HTTP MCP uses the Streamable HTTP transport, which is an MCP community standard.

</details>

<details>
<summary><b> 🔌 Use EchoMind as DSH's Permanent Memory Engine via MCP</b></summary>

DeepSeek Harness (DSH) is DeepSeek's agent framework. EchoMind ships a standard MCP gateway (stdio + Streamable HTTP) that can be consumed by DSH via its official bridge plugin `@deepseek-ai/dsh-mcp-client`, serving as DSH's permanent memory engine. **No EchoMind code changes are required.**

Once connected, EchoMind's 7 MCP tools are exposed to the DSH agent as `mcp__echomind__<tool>`: `echomind_retrieve`, `echomind_store`, `echomind_search`, `echomind_feedback` (drives RL self-optimization), `echomind_reflect`, `echomind_delete`, and `echomind_health`.

> The actual path to `mcp_gateway.py` depends on how EchoMind is installed (e.g. `~/.hermes/skills/echomind-memory/` for Hermes, or your `pip` location). Replace `<ECHOMIND_DIR>` below with your install path.

### Option 1: Enable temporarily (for testing)

Create `echomind.cordis.yml`:

```yaml
- insert:
    - id: memory-echomind
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: echomind
        transport: stdio
        command: python3
        args: ['<ECHOMIND_DIR>/adapters/mcp_gateway.py']
        cwd: !!js process.cwd()
```

Start DSH with the patch:

```bash
dsh web --patch "$PWD/echomind.cordis.yml"
```

> The exact command depends on your DSH install and profile (`dsh web` / `dsh headless` / bare `dsh`).

### Option 2: Persist into a DSH profile (recommended)

Write the `insert` block into DSH's actual patch file:

```bash
# Per-profile (<name> → e.g. web / headless)
$DSH_HOME/profiles/<name>/cordis.patch.yml

# Or machine-wide (all profiles)
$DSH_HOME/cordis.patch.yml
```

**Append** to the file—do not overwrite it, as it may already contain other user patches.

> ⚠️ DSH's stdio bridge strips credential-looking environment variables. To use API-key auth, pass `ECHOMIND_API_KEY` explicitly in `config.env`.

### Option 3: Remote HTTP mode (optional)

If the EchoMind HTTP service is already running (`python main.py`, port 8005):

```yaml
- insert:
    - id: memory-echomind
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: echomind
        transport: streamable-http
        url: http://127.0.0.1:8005/mcp
```

> ⚠️ HTTP MCP mode requires the EchoMind HTTP service to be running (`python main.py`). stdio mode is unaffected.

### Usage tip (reliability)

DSH's MCP bridge exposes tools only—it does not mount lifecycle hooks, so EchoMind cannot auto-inject memory per turn on the DSH side. Add a hint to DSH's agent/system prompt:

> When the user asks you to remember something, call `echomind_store`. When historical information may be relevant, call `echomind_search` / `echomind_retrieve` and use the results.

### Verification

1. Start DSH and confirm `mcp__echomind__echomind_health` etc. are registered (tool discovery is async—wait a moment).
2. In session A, have the model call `echomind_store` to record a uniquely-tagged memory and confirm success.
3. Open a new session B (without copying A), ask for that memory, and confirm the model calls `echomind_search`/`echomind_retrieve` and returns the right value.
</details>
