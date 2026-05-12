[![OpenClaw Compatible](https://img.shields.io/badge/OpenClaw-Compatible-brightgreen)](https://github.com/OpenClaw)
[![Hermes-Agent Ready](https://img.shields.io/badge/Hermes--Agent-Ready-blue)](https://github.com/Hermes-Agent)
[![Claude Code Supported](https://img.shields.io/badge/Claude%20Code-Supported-orange)](https://claude.ai/code)
[![OpenCode Compatible](https://img.shields.io/badge/OpenCode-Compatible-red)](https://github.com/open-code-ai)

# 🌟 EchoMind Skill —— 让你的 AI 拥有永久记忆与个人知识风格学习能力

> **全球首个支持 OpenClaw、Hermes-Agent、Claude Code (Cursor) 和 OpenCode 生态的长期记忆 Skill。**  
> 让你的 AI 不再“失忆”——记得你的偏好、研究方法、编码风格，甚至自我进化。

![Echomind Logo Concept](docs/logo-concept.png)

📦 项目地址
GitHub: https://github.com/yourusername/echomind_memory.skill
Star 它，让 AI 记得你。


---

## ✅ 支持框架

| 框架 | 支持方式 |
|------|----------|
| ✅ **OpenClaw** | 通过 `skill.yaml` + `main.py` 工具调用 |
| ✅ **Hermes-Agent** | 通过 `call()` 通用接口 |
| ✅ **Claude Code (Cursor)** | 自动写入 `.echomind/` 文件，AI 自动读取上下文 |
| ✅ **OpenCode (Devika / CodeAct)** | 通过 CLI + JSON Schema 标准化记忆格式 |

---

## ✨ 核心能力

| 功能 | 说明 |
|------|------|
| 🧠 **五类记忆系统** | Context / Task / User / Knowledge / Experience —— 完全遵循权威架构 |
| 📈 **强化学习自动优化** | 根据用户 👍/👎 反馈，AI 自动调整记忆权重，越用越聪明 |
| 🚀 **研究方向记忆** | 记录你的论文元数据、理论模型、算法方法、以及研究笔记 |
| 🧠 **研究方向高度扩展** | 可根据用户需要，扩展研究领域，用的越久越懂你的研究 |
| 🧑‍💻 **代码风格记忆** | 记录你是否喜欢 type hint、注释风格、函数长度、折行策略 |
| 🔁 **经验沉淀与复用** | “你上次修复了这个异常” “你经常用的研究模型” → 下次自动推荐相同解决方案 |
| 🗃️ **工业级持久化存储** | PostgreSQL（结构化） + ChromaDB（语义向量） + Redis（缓存） |
| 🚀 **一键部署** | `docker-compose up` 3秒启动全部依赖 |
| 🌐 **跨框架兼容** | 独立于任何 LLM，适配任何支持 Function Calling 的 Agent |

---

## 🚀 快速安装（3分钟上手）

### 1. 下载并解压本包
```bash
unzip echomind_memory.skill.zip
cd echomind_memory.skill
```

### 2. 安装 Python 依赖
```bash
pip install -r requirements.txt
```

### 3. 启动所有数据库服务（一键部署）
```bash
docker-compose up -d
```
✅ 自动创建：PostgreSQL（含 user_memory, task_memory, experience_memory 表）、Redis 缓存、ChromaDB 向量库

### 4. 配置（复制默认模板）
```bash
cp config.example.yaml config.yaml
```
修改 `postgres_url`、`chroma_path` 以匹配你的环境

### 5. 整合进你的 AI Agent
##### ➤ OpenClaw / Hermes-Agent
把整个 echomind_memory.skill/ 文件夹放入你的 skills/ 目录下 —— 框架将自动加载所有工具。

#### ➤ Claude Code / Cursor（关键！）
在你的 项目根目录 运行：

python -m echomind_memory.main sync_code_memory --user_id alice --project_root /path/to/your/project
→ 自动生成两个文件：

.echomind/context.json：结构化偏好与经验
.echomind/README.md：人类可读摘要

✅ Cursor 会自动读取这两个文件作为上下文！
示例：

当你写 def parse_date():，它会说：
“你上次在这里加了异常处理，风格偏好简洁，我按你习惯补全：”

#### ➤ OpenCode（Devika / CodeAct / Tabby）
调用 CLI 获取记忆：

python -m echomind_memory.code_format.cli read alice myproject
→ 输出标准化 JSON（符合 schema），你可直接注入 LLM prompt。

推荐在 Devika 的 context_builder.py 中调用它：
```python
memory = subprocess.check_output([
    "python", "-m", "echomind_memory.code_format.cli",
    "read", user_id, project_id
], text=True)
prompt += f"\n\n=== EchoMind Memory ===\n{memory}"
```

## ▶️ 使用示例（Python）
➤ 从 Agent 获取记忆（用于 LLM 提示词）
```python
from main import call
import asyncio
import json

async def main():
    result = await call("retrieve_memory", 
        user_id="alice", 
        query="这个函数怎么优化？", 
        task_id="task-abc"
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))

    # 将这段内容注入你的 LLM prompt 作为背景
    context = "\n".join([m["content"] for m in result["working_memory"]])
    print(f"\n📊 注入 LLM 的上下文：\n{context}")

asyncio.run(main())
```

## ➤ 同步记忆到 Cursor（让 AI 在 IDE 中“看见”你的习惯）
```python
from main import call
import asyncio

async def main():
    await call("sync_code_memory", 
        project_root="/home/alice/my-python-project", 
        user_id="alice"
    )
    print("✅ 已生成 .echomind/context.json 和 README.md")
    print("请在 Cursor 中打开此项目，AI 将自动感知你的风格！")

asyncio.run(main())
```

## ➤ 用户反馈闭环（AI 自我进化）
```python
from main import call
import asyncio

async def main():
    await call("record_feedback",
        user_id="alice",
        task_id="task-abc",
        feedback="positive",  # 👍
        retrieved_memories=[
            {
                "source": "experience",
                "content": "类似问题上次通过加异常处理解决",
                "importance": 0.9,
                "metadata": {}
            }
        ]
    )
    print("✅ 反馈已记录，权重已优化！")

asyncio.run(main())
```

## 🌐 愿景

AI 不是工具，是协作者。
协作者不应该每次见面都“重新认识你”。

EchoMind 让你的 AI：

记得你讨厌空行、喜欢 docstring

记得你修复过 auth.py 的 XSS 漏洞

记得你偏好用 半参数模型而不是协方差建模

记得你曾因为某个因子痛苦了 3 小时 → 下次自动避开

这不是一个插件，这是 AI 的多智能体记忆神经网络。






