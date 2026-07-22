## 安装

### 前置条件

确认已安装以下工具：

| 工具 | 检查命令 | 安装方式 |
|------|---------|---------|
| **Python 3.10+** | `python3 --version` | [python.org](https://python.org) |
| **pip** | `pip --version` | Python 自带 |
| **git** | `git --version` | `sudo apt install git` / [git-scm.com](https://git-scm.com) |

### 方式一：快速安装（推荐，含开机自启）

安装脚本负责复制文件、生成配置、注册自启。

```bash
# 步骤 1: 克隆仓库
git clone https://github.com/jasonatgit/echomind_memory.skill.git
cd echomind_memory.skill

# 步骤 2: 安装 Python 依赖
pip install -r requirements.txt

# 步骤 3: 运行安装脚本
./install.sh
```

**Windows（PowerShell）：**

```powershell
# 步骤 1: 克隆仓库
git clone https://github.com/jasonatgit/echomind_memory.skill.git
cd echomind_memory.skill

# 步骤 2: 安装 Python 依赖
pip install -r requirements.txt

# 步骤 3: 运行安装脚本
.\install.ps1
```

> **`install.sh` / `install.ps1` 做了什么：**
> 1. 自动检测 Hermes 安装目录（优先级: `$HERMES_HOME` → 平台默认）
>    - Linux/macOS/WSL: `~/.hermes`
>    - Windows: `%LOCALAPPDATA%\hermes`
> 2. 复制到 `<hermes>/skills/echomind-memory/`（Skill 目录）
> 3. 复制到 `<hermes>/plugins/echomind/`（MemoryProvider 插件）
> 4. 创建默认配置 `~/.echomind/echomind_config.yaml`（已存在则跳过）
> 5. 注册开机自启（systemd / launchd / 注册表）

**安装完成后验证：**

```bash
curl http://localhost:8005/health
# 预期返回: {"status": "ok", "version": "1.2.2"}
```

---

### 方式二：手工安装（不含开机自启）

适合不想注册自启的用户：

```bash
# 1. 克隆仓库并安装依赖（同方式一步骤 1-2）
git clone https://github.com/jasonatgit/echomind_memory.skill.git
cd echomind_memory.skill
pip install -r requirements.txt

# 2. 创建配置
mkdir -p ~/.echomind && cp echomind_config.yaml ~/.echomind/

# 3. 手动启动服务
python main.py
# 服务运行在 http://localhost:8005
```

> **提示：** 需要开机自启请使用上方方式一。

---

### Hermes-Agent 激活自动存取（推荐）

完成上述安装后，还需额外激活 Hermes 的 MemoryProvider 插件——这一步让 Hermes 每轮对话自动存取记忆，无需 LLM 决策：

```bash
# 1. 安装插件文件（一键安装已自动完成此步，手工安装需手动执行）
#    默认 Hermes 目录为 ~/.hermes，如不相同请自行调整（检查 HERMES_HOME）
cp -r echomind_memory.skill/* ~/.hermes/plugins/echomind/

# 2. 激活 MemoryProvider
hermes config set memory.provider echomind

# 3. 重启 Hermes 即可生效
```

**效果：** 每轮对话自动存入、自动检索。对话后自动触发自我反思——无需任何额外配置。

---

### Claude Code MCP 网关 (v1.2.0+)

启动 HTTP 服务后（`python main.py`），注册为 Claude Code MCP 服务器：

```bash
# 注册 MCP 网关（替换路径为你的安装位置）
claude mcp add echomind -- python ~/.hermes/skills/echomind-memory/adapters/mcp_gateway.py
```

**可用工具：** `echomind_retrieve`、`echomind_store`、`echomind_search`、`echomind_feedback`、`echomind_reflect`、`echomind_delete`、`echomind_health`

**效果：** Claude Code 可直接通过原生 MCP 工具读写 EchoMind 记忆——无需 HTTP API 调用。

---

### OpenClaw / OpenCode / Claude Code

将 EchoMind 安装到对应框架的 skills 目录，然后启动 HTTP 服务：

```bash
# 安装依赖
pip install -r requirements.txt

# 复制到框架 skills 目录（按需选择）
cp -r . ~/.openclaw/skills/echomind-memory/    # OpenClaw
cp -r . ~/.opencode/skills/echomind-memory/    # OpenCode

# 启动服务
python main.py
```

服务运行在 `http://localhost:8005`，LLM 根据 skill 触发规则自动调用记忆工具。

### Python 快速上手

```python
from main import call

# 存储记忆（平台感知）
call("store_memory",
    user_id="alice",
    platform="hermes",
    task_id="task-001",
    context=[{"role": "user", "content": "供应链协调有哪些常见模型"}],
    task_status="completed",
    success=True,
)
# 检索记忆
result = call("retrieve_memory", user_id="alice", query="供应链协调模型")
for m in result["working_memory"]:
    print(f"[{m['source']}] {m['content'][:80]}")
# 记录反馈（AI 自我进化）
call("record_feedback",
    user_id="alice",
    task_id="task-001",
    feedback="positive",
    retrieved_memories=result["working_memory"],
)

# 触发自我反思（v1.1.0）— Hermes 适配器自动调用
# 或通过 HTTP 手动触发：POST /api/reflect
```

---
