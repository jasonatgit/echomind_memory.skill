[![OpenClaw Compatible](https://img.shields.io/badge/OpenClaw-Compatible-brightgreen)](https://github.com/OpenClaw)
[![Hermes-Agent Ready](https://img.shields.io/badge/Hermes--Agent-Ready-blue)](https://github.com/Hermes-Agent)
[![Claude Code Supported](https://img.shields.io/badge/Claude%20Code-Supported-orange)](https://claude.ai/code)
[![OpenCode Compatible](https://img.shields.io/badge/OpenCode-Compatible-red)](https://github.com/open-code-ai)

# EchoMind Skill — Give Your AI Permanent Memory and Self-Evolving Knowledge

🌐 **中文版:** [README.zh-CN.md](README.zh-CN.md)

> A cross-platform long-term memory Skill for OpenClaw, Hermes-Agent, Claude Code (Cursor), and OpenCode.
> Your AI remembers your preferences, research methods, coding style — and self-evolves.

📦 **Repository:** https://github.com/jasonatgit/echomind_memory.skill


### Features

| Feature | Description |
|------|------|
| **Hermes Agent Memory Plugin** | Implements Hermes Agent memory interface for automatic per-turn read/write. Code-driven, no LLM decision required, 100% reliable |
| **Platform-Aware Memory** | All contextual memories tagged with platform (hermes/openclaw/opencode); same platform weight unchanged, cross-platform reduced; user preferences isolated by platform |
| **WAL Concurrent Mode** | Supports multi-process concurrent read/write |
| **Auto Migration** | Automatic migration with legacy data isolation |
| **Isolated User Preferences by Platform** | Different platforms (OpenClaw, OpenCode, etc.) have independent memory |

---

## Version History

### v1.0.10 — Hermes v0.14.0 Full Compatibility (2026-05-17)

**New (MemoryProvider ABC compliance):**

| Method | Description |
|------|------|
| `queue_prefetch()` | Compatible with Hermes v0.13.0+ new interface, eliminates per-turn AttributeError (was previously causing error logs on every turn) |
| `on_session_switch()` | Fixes session ID corruption after `/resume` `/branch` `/reset` operations |
| `on_pre_compress()` | Auto-saves memories before context compression discards them |
| `on_delegation()` | Captures sub-agent task experience into long-term memory |

**Fixes:**

| Item | Description |
|------|------|
| `agent_context` Filter | Auto-detects and skips `cron` / `subagent` / `flush` non-primary contexts to prevent memory contamination |
| `handle_tool_call` JSON | Tool call return value now uses JSON string format, compliant with Hermes ABC contract |
| Unified Write Guard | `prefetch` / `sync_turn` / `on_session_end` / `on_memory_write` now use unified `skip_writes` guard |

### v1.0.9 — OpenClaw / OpenCode / Claude Code Platform Fixes (2026-05-16)

| Fix | Platforms |
|--------|---------|
| `main.py` added `call()` dispatch function | OpenClaw |
| `http_api.py` retrieve/store endpoints pass `platform` param | All |
| `code_format/cli.py` fixed async→sync crash | OpenCode |
| `skill.yaml` added `platform` param + `openclaw.call` declaration | OpenClaw |

### v1.0.8 — Platform-Aware Memory + Hermes Adapter (2026-05-15)

- Platform-aware memory: same-platform weight ×1.0, cross-platform ×0.5
- Hermes Agent plugin: implements MemoryProvider interface, automatic per-turn read/write
- WAL concurrent mode + auto data migration



---

## Supported Platforms

| Platform | Integration | Reliability |
|----------|-------------|-------------|
| **Hermes-Agent** | Via `call()` generic interface | ★★★★★ 100% |
| **OpenClaw** | Via `skill.yaml` + `main.py` tool calls | ★★★★☆ LLM-decision |
| **OpenCode (Devika / CodeAct)** | Via CLI + JSON Schema standardized format | ★★★★☆ LLM-decision |
| **Claude Code (Cursor)** | Auto-write `.echomind/` files, AI auto-reads context | ★★★★☆ LLM-decision |

---

## Core Capabilities

| Capability | Description |
|------|------|
| **6 Memory Types** | Context / Task / User / Knowledge / Experience / Research |
| **RL Auto-Optimization** | AI automatically adjusts memory weights based on positive/negative feedback — gets smarter with every use |
| **Research Memory** | Stores paper metadata, theoretical models, algorithms, and research notes |
| **Code Style Memory** | Records your type hint, comment, and function length preferences |
| **Experience Reuse** | Previously fixed bugs / used models → auto-suggested next time |
| **Zero-Dependency Local Storage** | SQLite persistence, no Docker / PostgreSQL / Redis required |
| **Cross-Framework** | LLM-independent; adapts to OpenClaw / Hermes / Claude Code / OpenCode |

*Memory system optimized for **Management Science & Engineering** research. **All domains customizable**.*

### Auto-Retrieval

When queries touch these domains, research memory is automatically retrieved:

| Domain | Trigger Keywords |
|------|-----------|
| Operations Research | linear programming, integer programming, operations research |
| Supply Chain | supply chain, inventory, logistics |
| Decision Analysis | decision analysis, multi-criteria, AHP |
| Optimization | optimization, optimal, gradient |
| Simulation | simulation, Monte Carlo |
| Game Theory | game theory, Nash equilibrium |
| Forecasting | time series, forecasting |
| Project Management | critical path, project management |
| Queuing Theory | queuing |

| Feature | Description |
|---------|-------------|
| **Hermes Adapter Plugin** | Implements Hermes memory interface automatic read and write each cycle. Code-driven, no LLM decision required, 100% reliable |
| **Platform-aware Memory** | All contextual memories are tagged with the platform (hermes/openclaw/opencode); same platform weight ×1.0, cross-platform ×0.5; user preferences isolated by platform |
| **WAL Concurrent Mode** | Supports multi-process concurrent read and write |
| **Automatic Migration** | Automatic migration |
| **User Preferences Isolated by Platform** | Different users, different applications, different platforms have independent preferences, isolating your memory |

---

## Supported Platforms

## Quick Install

### One-Line Install

In OpenClaw, Hermes-agent, or OpenCode, simply say or copy/paste:
```bash
Install EchoMind skills from: https://github.com/jasonatgit/echomind_memory.skill
```

### 1. Install

| Capability | Description |
|------------|-------------|
| **6 Memory Types** | Context / Task / User / Knowledge / Experience / Research |
| **RL Auto-optimization** | Weights auto-adjust based on positive/negative feedback |
| **Research Memory** | Paper metadata, models, methods, notes |
| **Code Style Memory** | Type hints, comment style, function length, project conventions |
| **Experience Reuse** | Previously fixed bugs / used models → auto-suggest next time |
| **Zero-Dependency Storage** | Pure SQLite, no Docker/PostgreSQL/Redis required |
| **Cross-Framework** | LLM-independent; works with any platform that supports HTTP or MCP |

Only 3 packages: `pydantic` + `python-dotenv` + `numpy`. SQLite is a built-in Python module.

### 2. Integrate with Your AI Agent

When queries touch these domains, research memory is automatically retrieved:

Place the entire `echomind_memory.skill/` folder into your `skills/` directory — the framework will auto-load all tools.

The framework discovers tools via `skill.yaml`, then calls `main.call(tool_name, **kwargs)` for dispatch. No extra configuration needed.

## Quick Start

Run the sync command in your project root:

```bash
# Install as MemoryProvider plugin
cp -r echomind_memory.skill ~/.hermes/plugins/echomind/
hermes config set memory.provider echomind

Or call via code:

```python
from main import call
call("sync_code_memory", project_root="/path/to/project", user_id="alice")
```

Automatically generates two files for AI consumption:

- `.echomind/context.json`: Structured preferences and experience
- `.echomind/README.md`: Human-readable summary

#### OpenCode

Get standardized JSON memory via CLI:

```bash
python -m example.opencode_call alice "supply chain coordination model"
```

Output can be directly injected into LLM prompt:

# Start HTTP service
cd ~/.openclaw/skills/echomind-memory && python3 main.py
# or
cd ~/.opencode/skills/echomind-memory && python3 main.py
```

Service runs on `http://localhost:8005`. The LLM calls memory tools based on skill triggers.

## Quickstart

```python
import sys; sys.path.insert(0, '/path/to/echomind_memory.skill')
from core.memory_agent import MainMemoryAgent

# Initialize SQLite persistence (auto-creates ~/.echomind/memory.db)
init()

# Store memory
call("store_memory",
    user_id="alice",
    task_id="task-001",
    context=[{"role": "user", "content": "What are common supply chain coordination models?"}],
    task_status="completed",
    success=True,
    platform="hermes",  # or "openclaw", "opencode"
)

# Retrieve memory
result = call("retrieve_memory", user_id="alice", query="supply chain coordination")
for m in result["working_memory"]:
    print(f"[{m['source']}] {m['content'][:80]}")

# Record feedback (AI self-evolution)
call("record_feedback",
    user_id="alice",
    task_id="task-001",
    feedback="positive",
    retrieved_memories=result["retrieved_memories"],
)

agent.disable_persistence()
```

---

## Example Files

| File | Description |
|------|------|
| `example/hermes_call_example.py` | Full Hermes-Agent usage example |
| `example/openclaw_call.py` | Full OpenClaw usage example (with research papers) |
| `example/cursor_sync_example.py` | Claude Code / Cursor memory sync example |
| `example/opencode_call.py` | OpenCode CLI and API usage examples |

---

## Data Storage

All persistent data stored in `~/.echomind/memory.db` (SQLite file). Can be backed up or deleted at any time.

---

## Architecture

```
EchoMind Memory System (v1.0.10, Pure SQLite)
├── User Memory       (preferences/habits/RL weights)  → user_memory table
├── Task Memory       (task status/steps)               → task_memory table
├── Experience Memory (success/failure experiences)     → experience_memory table
├── Context Memory    (conversation context)            → context_memory table
├── Knowledge Memory  (domain knowledge)                → knowledge_memory table
├── Research Memory   (papers/notes)                    → research_papers + research_notes
└── RL Optimizer      (feedback self-optimization, persistent weights)
```

---

## Vision

AI is not a tool — it's a collaborator. A collaborator shouldn't have to "re-learn who you are" every session.

EchoMind gives your AI:

- Memory of your coding style, preferences, and habits
- Memory of bugs you've fixed and approaches you've tried
- Memory of your preference for semi-parametric models over covariance modeling
- Memory of that painful 3-hour debugging session → auto-avoid next time
- This isn't just a plugin. This is a multi-agent memory neural network for your AI.
