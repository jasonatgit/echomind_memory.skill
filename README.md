<p align="center">
  <img src="assets/banner.png" alt="echomind_memory.skill" width="100%">
</p>

[![OpenClaw Compatible](https://img.shields.io/badge/OpenClaw-Compatible-brightgreen)](https://github.com/OpenClaw)
[![Hermes-Agent Ready](https://img.shields.io/badge/Hermes--Agent-Ready-blue)](https://github.com/Hermes-Agent)
[![Claude Code Supported](https://img.shields.io/badge/Claude%20Code-Supported-orange)](https://claude.ai/code)
[![OpenCode Compatible](https://img.shields.io/badge/OpenCode-Compatible-red)](https://github.com/open-code-ai)


# EchoMind Memory Skill —— Give Your AI Permanent Memory and Self-Evolution Capabilities


🌐 **中文版:** [README.zh-CN.md](README.zh-CN.md)


> A long-term memory Skill supporting the Hermes Agent, OpenClaw, OpenCode, and Claude Code ecosystems.

> Stop your AI from "forgetting" — remember your preferences, style, research methods; self-reflect and self-evolve.

> EchoMind-Memory Skill helps you: extract knowledge from conversations, crystallize rules through reflection.


📦 **Repository:** https://github.com/jasonatgit/echomind_memory.skill



---

## EchoMind's Core Capabilities

| Capability | Description |
|------|------|
| **Self-Evolving Engine Agent** | Automatically reflects on raw memories to distill semantic knowledge and procedural rules, with zero-config LLM injection |
| **Seven Types of Memory** | User / Task / Experience / Context / Knowledge / Research / Reflection |
| **Ebbinghaus Forgetting Curve** | Freshness-based memory decay, auto-downranks stale memories |
| **RL-Enhanced Auto-Optimization** | Automatically adjusts memory weights based on positive/negative user feedback and persists them — gets smarter with use. Cosine learning rate decay + epsilon-greedy exploration to avoid local optima |
| **Few-Shot Anchoring** | Rapidly builds memory norms from small samples, improving memory quality |
| **Experience Distillation & Reuse** | Previously fixed bugs / used models → auto-recommended next time |
| **Multi-Trigger Retrieval** | Keywords + RL weights + LLM semantics, a true "semantic memory system" |
| **Hallucination-Prevention** | Long-term memory safety mechanism — low-confidence reflection results are automatically discarded to prevent hallucination pollution |
| **Platform-Aware Memory Isolation** | Cross-platform weight decay; isolation by user, project, session, topic, and research domain — no more memory chaos |
| **Zero-Dependency Local Storage** | SQLite persistence, no Docker / PostgreSQL / Redis required |
| **Cross-Framework Compatibility** | LLM-independent, adapters for Hermes / OpenClaw / OpenCode / Claude Code |

---

### Auto-Retrieval Triggers
EchoMind's memory system is optimized specifically for *research-oriented* memory, storing research papers, theoretical models, and research methodologies.

When a query involves the following *domain keywords* or related *semantics*, the system automatically retrieves research memories:

| Domain |
|------|
| Management Science |
| AI |
| NLP |
| Biology |
| Computer Science |
| Robotics |
| Speech & Audio |
| Recommendation Systems |
| Statistics & Decision Science |

**Other disciplines and keywords can all be customized**


---

## Supported Frameworks

| Framework | Integration Method | Reliability |
|------|----------|--------|
| **Hermes-Agent** | MemoryProvider Plugin (automatic, v0.13.0–v0.17.0) | ★★★★★ 100% |
| **OpenClaw** | `skill.yaml` + HTTP API tool invocation | ★★★★☆ LLM-decision |
| **OpenCode** | CLI + HTTP API or MCP stdio | ★★★★☆ LLM-decision |
| **Claude Code** | MCP stdio or HTTP API | ★★★★☆ LLM-decision |


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

## Installation

### Prerequisites

Make sure you have the following installed:

| Tool | Check | Install |
|------|-------|---------|
| **Python 3.10+** | `python3 --version` | [python.org](https://python.org) |
| **pip** | `pip --version` | Comes with Python |
| **git** | `git --version` | `sudo apt install git` / [git-scm.com](https://git-scm.com) |

### Option 1: Quick Install (Recommended, with Auto-Start)

The install script copies files, generates config, and registers auto-start.

```bash
# Step 1: Clone the repository
git clone https://github.com/jasonatgit/echomind_memory.skill.git
cd echomind_memory.skill

# Step 2: Install Python dependencies
pip install -r requirements.txt

# Step 3: Run the install script
./install.sh
```

**Windows (PowerShell):**

```powershell
# Step 1: Clone the repository
git clone https://github.com/jasonatgit/echomind_memory.skill.git
cd echomind_memory.skill

# Step 2: Install Python dependencies
pip install -r requirements.txt

# Step 3: Run the install script
.\install.ps1
```

> **What `install.sh` / `install.ps1` does:**
> 1. Detects your Hermes home directory automatically (priority: `$HERMES_HOME` → platform default)
>    - Linux/macOS/WSL: `~/.hermes`
>    - Windows: `%LOCALAPPDATA%\hermes`
> 2. Copies to `<hermes>/skills/echomind-memory/` (Skill directory)
> 3. Copies to `<hermes>/plugins/echomind/` (MemoryProvider plugin)
> 4. Creates default config `~/.echomind/echomind_config.yaml` (skips if exists)
> 5. *(optional)* Registers HTTP service auto-start — only when `ECHOMIND_HTTP_SERVICE=1` is set
>
> **Rationale:** The EchoMind MemoryProvider plugin runs **inside Hermes's process** —
> no separate HTTP service is needed for memory to work. The standalone HTTP API
> (`main.py`) is only required when integrating with OpenCode, OpenClaw, or other
> external tools that call memory over HTTP.

**Verify after installation:**

```bash
curl http://localhost:8005/health
# Expected: {"status": "ok", "version": "1.2.0"}
```

---

### Option 2: Manual Install (No Auto-Start)

If you prefer to start the service manually:

```bash
# 1. Clone and install deps (same as Option 1 steps 1-2)
git clone https://github.com/jasonatgit/echomind_memory.skill.git
cd echomind_memory.skill
pip install -r requirements.txt

# 2. Create config
mkdir -p ~/.echomind && cp echomind_config.yaml ~/.echomind/

# 3. Start the service manually
python main.py
# Service runs at http://localhost:8005
```

> **Tip:** For auto-start, use Option 1 above.

---

### Hermes-Agent Auto Memory (Recommended)

After completing the installation above, activate the MemoryProvider plugin — this enables Hermes to auto-save and auto-retrieve memories on every turn, no LLM decisions required:

```bash
# 1. Install plugin files (already done by one-click install; manual install requires this step)
cp -r echomind_memory.skill/* ~/.hermes/plugins/echomind/

# 2. Activate MemoryProvider
hermes config set memory.provider echomind

# 3. Restart Hermes to take effect
```

**Result:** Every turn auto-saved, auto-retrieved. Self-reflection auto-triggered after conversations — no additional configuration required.

---

### Claude Code MCP Gateway (v1.2.0+)

After starting the HTTP service (`python main.py`), register EchoMind as a Claude Code MCP server:

```bash
# Register the MCP gateway (replace path with your install location)
claude mcp add echomind -- python ~/.hermes/skills/echomind-memory/adapters/mcp_gateway.py
```

**Available tools:** `echomind_retrieve`, `echomind_store`, `echomind_search`, `echomind_feedback`, `echomind_reflect`, `echomind_delete`, `echomind_health`

**Result:** Claude Code can read/write your EchoMind memories as native MCP tools — no HTTP API calls needed.

---

### OpenClaw / OpenCode / Claude Code

Install EchoMind to your framework's skills directory, then start the HTTP service:

```bash
# Install dependencies
pip install -r requirements.txt

# Copy to framework skills directory (choose as needed)
cp -r . ~/.openclaw/skills/echomind-memory/    # OpenClaw
cp -r . ~/.opencode/skills/echomind-memory/    # OpenCode

# Start service
python main.py
```

Service runs at `http://localhost:8005`. LLM invokes memory tools based on skill trigger rules.

### Python Quick Start

```python
from main import call

# Store memory (platform-aware)
call("store_memory",
    user_id="alice",
    platform="hermes",
    task_id="task-001",
    context=[{"role": "user", "content": "What are common supply chain coordination models?"}],
    task_status="completed",
    success=True,
)
# Retrieve memory
result = call("retrieve_memory", user_id="alice", query="supply chain coordination models")
for m in result["working_memory"]:
    print(f"[{m['source']}] {m['content'][:80]}")
# Record feedback (AI self-evolution)
call("record_feedback",
    user_id="alice",
    task_id="task-001",
    feedback="positive",
    retrieved_memories=result["working_memory"],
)

# Trigger self-reflection (v1.1.0) — Hermes adapter calls automatically
# Or trigger manually via HTTP: POST /api/reflect
```

---

## API Endpoints (HTTP Mode)

| Method | Endpoint | Description |
|------|------|------|
| `POST` | `/api/memory/retrieve` | Retrieve task memory (with `platform` parameter support) |
| `POST` | `/api/memory/store` | Store conversation context (with `platform` parameter support) |
| `POST` | `/api/memory/feedback` | Record feedback for RL optimization |
| `POST` | `/api/memory/sync-code` | Sync project code style memory |
| `POST` | `/api/research/paper` | Add research paper |
| `POST` | `/api/research/note` | Add research note |
| `GET` | `/api/research/papers` | List research papers |
| `POST` | `/api/reflect` 🆕 | Self-reflection |
| `GET` | `/health` | Health check |

---

## Data Storage

All persistent data is stored in `~/.echomind/memory.db` (SQLite file). Can be backed up or deleted at any time. The storage path can be customized via `storage.db_path` in `echomind_config.yaml`.


---

## Vision

AI is not a tool, it's a collaborator. Collaborators shouldn't have to "re-meet you" every time.

EchoMind enables your AI to:

- Remember your coding style, preferences, and habits
- Remember the bugs you've fixed and approaches you've tried
- Remember the papers and theoretical models you've researched
- Possess an RL-driven self-optimizing weight system — gets smarter with every interaction
- This is not a plugin, this is an **AI Multi-Agent Memory Neural Network** with *self-reflective memory*.



---
## Contact
*email：*[jasonyouatgmaildotcom](mailto:jasonyouatgmaildotcom)


---
## Q&A *Click to expand*

<details>
<summary><b>Hermes Agent Profile Isolation & FAQ</b></summary>

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

