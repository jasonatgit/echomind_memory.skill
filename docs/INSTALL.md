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
# Expected: {"status": "ok", "version": "1.2.2"}
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
