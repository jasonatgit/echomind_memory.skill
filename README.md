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

## EchoMind's 10 Core Capabilities

| Capability | Description |
|------|------|
| **Self-Evolving Engine Agent** 🆕 | Automatically reflects on raw memories to distill semantic knowledge and procedural rules, with zero-config LLM injection |
| **Seven Types of Memory** | User / Task / Experience / Context / Knowledge / Research / Reflection |
| **RL-Enhanced Auto-Optimization** | Automatically adjusts memory weights based on positive/negative user feedback and persists them — gets smarter with use |
| **Few-Shot Anchoring** | Rapidly builds memory norms from small samples, improving memory quality |
| **Experience Distillation & Reuse** | Previously fixed bugs / used models → auto-recommended next time |
| **Multi-Trigger Retrieval** | Keywords + RL weights + LLM semantics, a true "semantic memory system" |
| **Hallucination-Prevention** 🆕 | Long-term memory safety mechanism — low-confidence reflection results are automatically discarded to prevent hallucination pollution |
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
| **Hermes-Agent** | MemoryProvider Plugin (automatic) | ★★★★★ 100% |
| **OpenClaw** | `skill.yaml` + HTTP API tool invocation | ★★★★☆ LLM-decision |
| **OpenCode** | CLI + HTTP API or MCP stdio | ★★★★☆ LLM-decision |
| **Claude Code** | MCP stdio or HTTP API | ★★★★☆ LLM-decision |


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

At the same time, EchoMind-Memory.skill's "self-evolution" primarily differs from the above scientific research in its adoption of **dependency inversion** (core engine with zero LLM coupling), **platform-aware isolation**, and **zero-configuration deployment** — making it directly usable in production Multi-Agent systems without additional infrastructure.

---

## Historical Version Notes

### v1.0.10 — Full Hermes v0.14.0 Compatibility (2026-05-17)

**Added (MemoryProvider ABC compatibility):**

| Method | Description |
|------|------|
| `queue_prefetch()` | Compatible with the new Hermes v0.13.0+ interface, eliminating per-turn AttributeError logs |
| `on_session_switch()` | Fixes session_id corruption after `/resume` `/branch` `/reset` operations |
| `on_pre_compress()` | Auto-saves memories about to be discarded before context compression |
| `on_delegation()` | Captures sub-agent task experience into long-term memory |

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

## Quick Install

### One-Line Install (Fastest & Easiest)

In OpenClaw, Hermes-agent, or OpenCode, simply say or copy/paste:

```bash
Install EchoMind-Memory.skill and start the service. Download: https://github.com/jasonatgit/echomind_memory.skill
```

### 1. Installation

### Hermes-Agent (Recommended — 100% Auto Save/Load)

```bash
# Install as MemoryProvider plugin
cp -r echomind_memory.skill ~/.hermes/plugins/echomind/
hermes config set memory.provider echomind

# Start Hermes — EchoMind auto-initializes
hermes
```

**Result:** Every turn auto-saved, auto-retrieved. No LLM decisions needed, no manual operations. Self-reflection auto-triggered after conversations — no additional configuration required.

### OpenClaw / OpenCode / Claude Code (HTTP Mode)

```bash
# Install dependencies
pip install -r requirements.txt

# Start HTTP service
cd ~/.openclaw/skills/echomind-memory && python3 main.py
# or
cd ~/.opencode/skills/echomind-memory && python3 main.py
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
- This is not a plugin, this is a **Multi-Agent Memory Neural Network** with *self-reflective memory*.