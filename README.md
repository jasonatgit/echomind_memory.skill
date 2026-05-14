[![OpenClaw Compatible](https://img.shields.io/badge/OpenClaw-Compatible-brightgreen)](https://github.com/OpenClaw)
[![Hermes-Agent Ready](https://img.shields.io/badge/Hermes--Agent-Ready-blue)](https://github.com/Hermes-Agent)
[![Claude Code Supported](https://img.shields.io/badge/Claude%20Code-Supported-orange)](https://claude.ai/code)
[![OpenCode Compatible](https://img.shields.io/badge/OpenCode-Compatible-red)](https://github.com/open-code-ai)

# EchoMind Memory — Give Your AI Permanent Memory


🌐 **中文版:** [README.zh-CN.md](README.zh-CN.md) 


> A cross-platform long-term memory system for AI agents.
> Your AI remembers your preferences, research methods, coding style — and self-evolves.

📦 **Repository:** https://github.com/jasonatgit/echomind_memory.skill



---



### What's New in v1.0.8

| Feature | Description |
|---------|-------------|
| **Hermes Adapter Plugin** | Implements Hermes memory interface automatic read and write each cycle. Code-driven, no LLM decision required, 100% reliable |
| **Platform-aware Memory** | All contextual memories are tagged with the platform (hermes/openclaw/opencode); same platform weight ×1.0, cross-platform ×0.5; user preferences isolated by platform |
| **WAL Concurrent Mode** | Supports multi-process concurrent read and write |
| **Automatic Migration** | Automatic migration |
| **User Preferences Isolated by Platform** | Different users, different applications, different platforms have independent preferences, isolating your memory |

---

## Supported Platforms

| Platform | Integration | Reliability |
|----------|-------------|-------------|
| **Hermes-Agent** | MemoryProvider plugin (auto) | ★★★★★ 100% |
| **OpenClaw** | `skill.yaml` + HTTP API tool calls | ★★★★☆ LLM-decision |
| **OpenCode** | CLI + HTTP API or MCP stdio | ★★★★☆ LLM-decision |
| **Claude Code** | MCP stdio or HTTP API | ★★★★☆ LLM-decision |

---

## Core Capabilities

| Capability | Description |
|------------|-------------|
| **6 Memory Types** | Context / Task / User / Knowledge / Experience / Research |
| **RL Auto-optimization** | Weights auto-adjust based on positive/negative feedback |
| **Research Memory** | Paper metadata, models, methods, notes |
| **Code Style Memory** | Type hints, comment style, function length, project conventions |
| **Experience Reuse** | Previously fixed bugs / used models → auto-suggest next time |
| **Zero-Dependency Storage** | Pure SQLite, no Docker/PostgreSQL/Redis required |
| **Cross-Framework** | LLM-independent; works with any platform that supports HTTP or MCP |

*The memory system is optimized for **Management Science & Engineering** research but supports any domain.*

### Auto-Retrieval Triggers

When queries touch these domains, research memory is automatically retrieved:

Operations Research, Supply Chain, Decision Analysis, Optimization, Simulation, Game Theory, Forecasting, Project Management, Queuing Theory

---

## Quick Start

### Hermes-Agent (Recommended — 100% Automatic)

```bash
# Install as MemoryProvider plugin
cp -r echomind_memory.skill ~/.hermes/plugins/echomind/
hermes config set memory.provider echomind

# Start Hermes — EchoMind auto-initializes
hermes
```

**Effect:** Every turn is automatically stored and retrieved. No LLM decisions, no manual steps.

### OpenClaw / OpenCode / Claude Code (HTTP Mode)

```bash
# Install dependencies
pip install -r requirements.txt

# Start HTTP service
cd ~/.openclaw/skills/echomind-memory && python3 main.py
# or
cd ~/.opencode/skills/echomind-memory && python3 main.py
```

Service runs on `http://localhost:8005`. The LLM calls memory tools based on skill triggers.

### Python Quickstart

```python
import sys; sys.path.insert(0, '/path/to/echomind_memory.skill')
from core.memory_agent import MainMemoryAgent

agent = MainMemoryAgent()
agent.enable_persistence()

# Store memory (platform-aware)
agent.store(
    user_id="alice",
    task_id="task-001",
    context=[{"role": "user", "content": "What are common supply chain coordination models?"}],
    task_status="completed",
    success=True,
    platform="hermes",  # or "openclaw", "opencode"
)

# Retrieve memory
result = agent.retrieve_for_task(
    task_context="supply chain coordination",
    user_id="alice",
    platform="hermes",
)
for m in result["retrieved_memories"]:
    print(f"[{m.source}] {m.content[:80]} (importance={m.importance})")

# Record feedback (RL self-evolution)
agent.record_feedback(
    user_id="alice",
    task_id="task-001",
    feedback="positive",
    retrieved_memories=result["retrieved_memories"],
)

agent.disable_persistence()
```

---

## API Endpoints (HTTP Mode)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/memory/retrieve` | Retrieve memories for a task (supports `platform` param) |
| `POST` | `/api/memory/store` | Store conversation context (supports `platform` param) |
| `POST` | `/api/memory/feedback` | Record feedback for RL optimization |
| `POST` | `/api/memory/sync-code` | Sync code-style memory from a project |
| `POST` | `/api/research/paper` | Add a research paper |
| `POST` | `/api/research/note` | Add a research note |
| `GET` | `/api/research/papers` | List research papers |
| `GET` | `/health` | Health check |

---

## Data Storage

All persistent data is stored in `~/.echomind/memory.db` (SQLite). Backup or delete at any time.

7 tables in a single file, zero infrastructure.

---

## Project Structure

```
echomind_memory.skill/
├── core/                  ← Platform-agnostic engine
│   ├── __init__.py
│   ├── memory_agent.py    ← 6 Agents + RL
│   ├── storage/
│   │   └── sqlite_store.py ← 7 tables (WAL mode)
│   ├── models/            ← Pydantic schemas
│   └── learning/          ← RL weight optimizer
├── adapters/              ← Platform adapters
│   ├── hermes_provider.py ← Hermes MemoryProvider
│   └── http_api.py        ← FastAPI HTTP
├── main.py                ← Unified entry point
├── plugin.yaml            ← Hermes plugin metadata
├── skill.yaml             ← OpenClaw tool definitions
├── example/               ← Usage examples per platform
├── code_format/           ← OpenCode CLI integration
├── README.md              ← This file (English)
├── README.zh-CN.md        ← Chinese version
└── doc/                   ← Documentation & changelog
```

---

## Vision

AI is not a tool — it's a collaborator. A collaborator shouldn't have to "re-learn who you are" every session.

EchoMind gives your AI:

- Memory of your coding style, preferences, and habits
- Memory of bugs you've fixed and approaches you've tried
- Memory of research papers and theoretical models you've explored
- An RL-powered self-improving weight system that gets smarter with every interaction

This isn't just a plugin. This is a multi-agent memory neural network for your AI.