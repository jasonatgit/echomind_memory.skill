# EchoMind v1.1.0 过渡方案 — 配置化 + .so 加密 + 技能发布

> **目标**：v1.0.10 → v1.1.0 平滑过渡，一套代码库零分支维护，  
> Prompts + 参数配置化，反思模块 .so 加密保护，  
> 按 Skill 发布规范输出完整实现文档。

---

## 目录

1. 现状分析
2. 架构总览
3. 配置层实现（ConfigManager）
4. Prompts 抽取
5. 硬编码参数迁移
6. .so 加密与条件加载（Cython）
7. v1.0.10 ↔ v1.1.0 过渡机制
8. 发布与安装
9. 实施路线（6 Phase，12 小时）
10. 附录

---

## 一、现状分析

### 1.1 代码规模

| 文件 | 行数 | 说明 |
|------|------|------|
| `core/reflective_agent.py` | 289 | 1 个硬编码 Prompt + 3 个参数 |
| `core/memory_agent.py` | 709 | 17 个硬编码参数 + domain_map |
| `core/learning/rl_weight_optimizer.py` | 127 | 6 个硬编码参数 |
| `adapters/hermes_provider.py` | 473 | LLM 调用参数 + 硬编码 URL |
| `adapters/http_api.py` | 222 | port 硬编码 |
| `main.py` | 143 | port 硬编码 |
| **总计** | **1963** | |

### 1.2 需抽取的硬编码项

| 类别 | 项数 | 关键项 |
|------|------|--------|
| RL 权重初始值 | 5 | relevance=0.4, recency=0.2, ... |
| RL 超参数 | 3 | learning_rate=0.07, decay_factor=0.97, max_buffer_size=50 |
| 反思触发参数 | 4 | batch_size=8, min_confidence=0.6, min_records=6, max_daily=10 |
| 检索参数 | 6 | top_k=5, min_success_rate=0.7/0.6, limit=3/5, preference_boost=0.2 |
| 网络参数 | 3 | llm_host=localhost:9119, timeout=60, http_port=8005 |
| Prompt 全文 | 1 | 反思蒸馏 Prompt (34 行) |
| 领域关键词 | 9 | domain_map 完整内容 |
| 偏好推理关键词 | 6 | infer 关键词列表 |
| **合计** | **37** | |

< 详见附录 A 完整参数映射 >

### 1.3 现状矛盾

- `plugin.yaml` 写 v1.0.10，`__init__.py` 写 v1.1.0，不一致
- main 分支为 v1.0.10（稳定版），`save/v1.1.0-work` 分支有 v1.1.0 代码但不敢推
- 反思 Prompt 硬编码在 Python 代码中，无法定制
- 领域切换需改代码

---

## 二、架构总览

```
echomind_memory.skill/
├── echomind_config.yaml          ← (新增) 全量配置
├── prompts/                       ← (新增) Prompt 模板目录
│   ├── reflection_distill.txt    ← 蒸馏 Prompt
│   └── reflection_refine.txt     ← 两阶段验证(预留)
├── core/
│   ├── config_manager.py         ← (新增) 统一配置管理
│   ├── reflective_agent.py       ← (改造) 接口+加载器+条件导入
│   ├── _reflective_core.pyx      ← (新增) Cython 源文件(不发布)
│   ├── _reflective_core.so       ← (新增) 编译产物(发布)
│   ├── _reflective_fallback.py   ← (新增) 开源 fallback
│   ├── memory_agent.py           ← (改造) 参数→config
│   ├── learning/rl_weight_optimizer.py ← (改造) 参数→config
│   └── models/reflection.py      ← 不变
├── adapters/
│   ├── hermes_provider.py        ← (改造) LLM参数→config
│   └── http_api.py               ← (改造) port→config
├── main.py                       ← (改造) port→config
├── plugin.yaml                   ← 版本: v1.0.10
├── __init__.py                   ← 版本: self.__version__
├── setup.py                      ← (新增) Cython 编译
├── install.sh                    ← (新增) 一键安装
└── SKILL.md                      ← (更新) 技能文档
```

### 核心设计

```python
# reflective_agent.py 条件加载
try:
    from ._reflective_core import (
        _build_prompt as _so_build_prompt,
    )
    _SO_LOADED = True
    logger.info("ReflectiveAgent: protected mode (.so loaded)")
except ImportError:
    from ._reflective_fallback import (
        _build_prompt as _fb_build_prompt,
    )
    _SO_LOADED = False
    logger.info("ReflectiveAgent: open-source mode (fallback)")
```

---

## 三、配置层实现（ConfigManager）

### 3.1 配置文件结构

```yaml
# echomind_config.yaml
# 优先级: API运行时覆盖 > YAML文件 > .so内置默认值 > 代码默认值

version: 2
prompts_dir: "prompts"

rl:
  initial_weights:
    relevance: 0.40
    recency: 0.20
    frequency: 0.15
    explicit_feedback: 0.15
    trust_score: 0.10
  learning_rate: 0.07
  decay_factor: 0.97
  max_buffer_size: 50

reflection:
  batch_size: 8
  min_confidence: 0.6
  min_records: 6
  max_daily: 10
  max_tokens: 1500
  max_rounds: 1

retrieval:
  experience_top_k: 5
  experience_min_success_rate:
    initial: 0.7
    final: 0.6
  context_limit: 2
  preference_score_boost: 0.2

llm:
  host: "localhost"
  port: 9119
  model: "local"
  temperature: 0.3
  max_tokens: 1500
  timeout: 60

server:
  host: "0.0.0.0"
  port: 8005

domain:
  default: "general"
  keywords:
    operations_research:
      zh: ["运筹学","线性规划","整数规划","网络优化","排队论"]
      en: ["operations research","linear programming","integer programming","queuing theory"]
    supply_chain:
      zh: ["供应链","物流","库存","配送"]
      en: ["supply chain","logistics","inventory","distribution"]
    # ... 9 个领域完整内容（见附录 B）

inference:
  min_occurrence: 2
  strategy: "keyword"
  keywords:
    concise_response: ["简短","简洁"]
    detailed_type: ["type hint","Optional[str]"]
    concise_code: ["简洁","不要注释"]
```

### 3.2 ConfigManager 实现

```python
# core/config_manager.py — 统一配置管理
import os
import yaml
import logging
from typing import Any, Dict, Optional
from pathlib import Path

logger = logging.getLogger("ConfigManager")

DEFAULT_CONFIG_PATH = os.path.expanduser("~/.echomind/echomind_config.yaml")
SO_CONFIG = None  # .so 可选注入

# 代码绝对默认值
FALLBACK_CONFIG = {
    "rl": {
        "initial_weights": {
            "relevance": 0.4, "recency": 0.2, "frequency": 0.15,
            "explicit_feedback": 0.15, "trust_score": 0.1,
        },
        "learning_rate": 0.07, "decay_factor": 0.97,
        "max_buffer_size": 50,
    },
    "reflection": {
        "batch_size": 8, "min_confidence": 0.6, "min_records": 6,
        "max_daily": 10, "max_tokens": 1500, "max_rounds": 1,
    },
    "retrieval": {
        "experience_top_k": 5,
        "experience_min_success_rate": {"initial": 0.7, "final": 0.6},
        "context_limit": 2, "preference_score_boost": 0.2,
    },
    "llm": {
        "host": "localhost", "port": 9119, "model": "local",
        "temperature": 0.3, "max_tokens": 1500, "timeout": 60,
    },
    "server": {"host": "0.0.0.0", "port": 8005},
    "domain": {"default": "general"},
    "inference": {"min_occurrence": 2, "strategy": "keyword"},
}


class ConfigManager:
    """配置管理器 — 分层读取：运行时 > YAML > .so > 代码默认"""

    def __init__(self, config_path: Optional[str] = None, so_config: Optional[dict] = None):
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self._so_config = so_config
        self._runtime_overrides: Dict[str, Any] = {}
        self._yaml_cache: Dict[str, Any] = {}
        self._load_yaml()
        self.version = self._yaml_cache.get("version", 2)

    def _load_yaml(self):
        path = Path(self.config_path)
        if path.exists():
            try:
                with open(path) as f:
                    self._yaml_cache = yaml.safe_load(f) or {}
                logger.info(f"Config loaded from {self.config_path}")
            except Exception as e:
                logger.warning(f"Config load failed: {e}, using defaults")
                self._yaml_cache = {}

    def get(self, key: str, *sections: str, default: Any = None) -> Any:
        """获取配置值。支持点号路径，如 get('reflection','batch_size')"""
        # 1. 运行时覆盖
        override_key = ".".join([key] + list(sections))
        if override_key in self._runtime_overrides:
            return self._runtime_overrides[override_key]

        # 2. YAML
        result = self._yaml_cache
        for part in [key] + list(sections):
            if isinstance(result, dict):
                result = result.get(part)
            else:
                result = None
                break
        if result is not None:
            return result

        # 3. .so 内置默认
        if self._so_config:
            result = self._so_config
            for part in [key] + list(sections):
                if isinstance(result, dict):
                    result = result.get(part)
                else:
                    result = None
                    break
            if result is not None:
                return result

        # 4. 代码绝对默认
        result = FALLBACK_CONFIG
        for part in [key] + list(sections):
            if isinstance(result, dict):
                result = result.get(part)
            else:
                result = None
                break
        return result if result is not None else default

    def get_section(self, key: str) -> dict:
        """获取完整配置节"""
        # 返回合并结果：runtime ∪ yaml ∪ so ∪ fallback
        merged = {}
        for source in [FALLBACK_CONFIG, self._so_config or {},
                       self._yaml_cache, self._runtime_overrides]:
            section = source.get(key) if isinstance(source, dict) else None
            if isinstance(section, dict):
                merged.update(section)
        return merged

    def set_runtime(self, key: str, value: Any):
        """运行时覆盖参数"""
        self._runtime_overrides[key] = value
        logger.info(f"Runtime override: {key} = {value}")

    def reload(self):
        """重新加载 YAML 配置文件"""
        self._yaml_cache = {}
        self._load_yaml()

    def validate(self, config: dict) -> list:
        """验证配置合法性，返回问题列表"""
        issues = []
        # 验证必要节
        required_sections = ["rl", "reflection"]
        for section in required_sections:
            if section not in config and section not in self._yaml_cache:
                issues.append(f"Missing section: {section}")
        # 验证数值范围
        reflection = config.get("reflection", self._yaml_cache.get("reflection", {}))
        if reflection.get("batch_size", 8) < 3:
            issues.append("reflection.batch_size must be >= 3")
        if reflection.get("min_confidence", 0.6) < 0.1 or reflection.get("min_confidence", 0.6) > 1.0:
            issues.append("reflection.min_confidence must be in [0.1, 1.0]")
        if config.get("rl", {}).get("learning_rate", 0.07) > 0.2:
            issues.append("rl.learning_rate must be <= 0.2")
        return issues


# 全局单例
_config_manager: Optional[ConfigManager] = None


def get_config_manager(config_path: Optional[str] = None) -> ConfigManager:
    """获取全局配置管理器单例"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager(config_path)
    return _config_manager
```

### 3.3 安装位置

```
~/.echomind/echomind_config.yaml    # 用户配置文件
                                    # 默认由 install.sh 生成
```

---

## 四、Prompts 抽取

### 4.1 目录结构

```
prompts/
  reflection_distill.txt     ← 蒸馏 Prompt（立即可用）
  reflection_refine.txt      ← 两阶段验证（v1.2 预留）
```

### 4.2 `prompts/reflection_distill.txt`

```text
You are EchoMind's Self-Reflective Agent — a memory distillation expert 
for AI coding assistants.

Your task: analyze recent episodic records and extract durable, 
generalizable knowledge.

RECENT EPISODIC RECORDS:
${context}

Perform deep reflection and output STRICTLY as JSON (no other text):

{
  "key_insights": ["insight1", "insight2", ...],
  "user_preferences": ["language=en", "response_style=concise", ...],
  "procedural_rules": ["if CONDITION -> take ACTION", ...],
  "new_knowledge": ["project X uses port 8001", ...],
  "forget_suggestions": ["temporary test data", ...],
  "confidence": 0.82
}

RULES:
- Extract GENERALIZABLE patterns, NOT specific code snippets
- User preferences: "key=value" format
- Procedural rules: "if CONDITION -> take ACTION" format
- Confidence: be HONEST — if little to extract, use low confidence (< 0.6)
- If nothing valuable, output empty lists with confidence=0.0
```

### 4.3 代码改造（`_build_reflection_prompt`）

```python
# reflective_agent.py 中
def _build_reflection_prompt(self, context: str) -> str:
    """委托给 .so 或 fallback 或 Prompt 文件"""
    if _SO_LOADED:
        return _build_prompt(context, self.config)
    
    # Fallback 1: 从 prompts/ 目录读取
    prompt_dir = self.config_manager.get("prompts_dir", default="prompts")
    prompt_path = Path(prompt_dir) / "reflection_distill.txt"
    if prompt_path.exists():
        template = string.Template(prompt_path.read_text(encoding="utf-8"))
        return template.safe_substitute(context=context)
    
    # Fallback 2: 代码内置
    return self._fallback_build_prompt(context)

def _fallback_build_prompt(self, context: str) -> str:
    """开源 fallback 版本：简单 Prompt"""
    return f"""Summarize these episodic records and extract general knowledge:

{context}

Output JSON as: key_insights, user_preferences, procedural_rules, 
new_knowledge, forget_suggestions, confidence"""
```

### 4.4 加载优先级

```
.so 内置 Prompt（最完整、带 Few-Shot 示例）
  ↓ prompts/reflection_distill.txt（用户可定制）
    ↓ _fallback_build_prompt（代码内置，最简版）
```

---

## 五、硬编码参数迁移

### 5.1 迁移对照

| 文件 | 行号 | 硬编码 | → 配置文件路径 | 修改方式 |
|------|------|--------|---------------|---------|
| `reflective_agent.py:38-42` | `config = {"batch_size":8,...}` | → `get_section("reflection")` | 替换 dict | 
| `reflective_agent.py:104` | `threshold = self.config.get("min_confidence", 0.6)` | → `self.config.get("min_confidence")` | 删除 fallback | 
| `memory_agent.py:269-275` | `RLWeightOptimizer(initial_weights={...})` | → `get_section("rl")` | 替换参数 | 
| `memory_agent.py:397-412` | `domain_map = {...}` | → `get("domain","keywords")` | 替换函数体 | 
| `memory_agent.py:426-443` | `top_k=5, min_success_rate=0.7` | → `get_section("retrieval")` | 提取常量 | 
| `memory_agent.py:644-656` | `infer keywords` | → `get("inference","keywords")` | 提取列表 | 
| `rl_weight_optimizer.py:32` | `max_buffer_size=50` | → `get("rl","max_buffer_size")` | 参数提取 | 
| `hermes_provider.py:458-466` | `localhost:9119, timeout=60` | → `get_section("llm")` | 替换 URL | 
| `hermes_provider.py:337` | `count=8` | → `get("reflection","min_records")` | 替换常量 | 
| `http_api.py:222` | `port=` | → `get("server","port")` | 替换端口 | 
| `main.py:139` | `port=8005` | → `get("server","port")` | 替换端口 | 

### 5.2 MainMemoryAgent 改动

```python
# memory_agent.py — MainMemoryAgent.__init__
def __init__(self, db_path: str = None, config_manager=None):
    self.cfg = config_manager or get_config_manager()
    
    # 从 ConfigManager 读取
    rl_config = self.cfg.get_section("rl")
    self.rl_optimizer = RLWeightOptimizer(
        initial_weights=rl_config.get("initial_weights", {
            "relevance": 0.4, "recency": 0.2, "frequency": 0.15,
            "explicit_feedback": 0.15, "trust_score": 0.1,
        }),
        learning_rate=rl_config.get("learning_rate", 0.07),
        decay_factor=rl_config.get("decay_factor", 0.97),
    )
    
    ref_config = self.cfg.get_section("reflection")
    self.reflective = ReflectiveAgent(self.db, self, config=ref_config)
```

### 5.3 `_detect_research_domain` 重构

```python
# memory_agent.py — domain_map 从代码移到配置文件
def _detect_research_domain(self, text: str) -> str:
    """从配置文件加载领域关键词"""
    domain_keywords = self.cfg.get("domain", "keywords", default={})
    t = text.lower()
    for domain_id, keywords in domain_keywords.items():
        all_kw = keywords.get("zh", []) + keywords.get("en", [])
        if any(k.lower() in t for k in all_kw):
            return domain_id
    return self.cfg.get("domain", "default", default="general")
```

### 5.4 `_hermes_llm_fn` 改造

```python
# hermes_provider.py
def _hermes_llm_fn(prompt: str) -> str:
    cfg = get_config_manager().get_section("llm")
    url = f"http://{cfg['host']}:{cfg['port']}/v1/chat/completions"
    try:
        resp = requests.post(url, json={
            "model": cfg.get("model", "local"),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": cfg.get("temperature", 0.3),
            "max_tokens": cfg.get("max_tokens", 1500),
        }, timeout=cfg.get("timeout", 60))
        ...
```

---

## 六、.so 加密与条件加载

### 6.1 Cython 源文件

```python
# core/_reflective_core.pyx (Cython 源文件，不发布)
# 包含:
# 1. _build_prompt — 完整反思 Prompt + Few-Shot 注入
# 2. _parse_result_advanced — JSON 修复 + 置信度校验
# 3. _get_optimized_defaults — 调优后的默认参数

def _build_prompt(str context, dict config):
    """构建高质量反思 Prompt"""
    cdef str prompt = (
        "You are EchoMind's Self-Reflective Agent — a memory distillation expert.\n\n"
        "Your task: analyze recent episodic records and extract durable knowledge.\n\n"
        "RECENT RECORDS:\n" + context + "\n\n"
        "...[完整 Prompt 编译到 .so 字符串常量]..."
    )
    return prompt


def _parse_result_advanced(str raw, dict config):
    """高级 JSON 解析 + 格式修复"""
    cdef str cleaned = raw.strip()
    cdef bint conf_check = False
    
    # 修复常见 LLM 输出错误
    if cleaned.startswith("```"):
        cleaned = cleaned[cleaned.index("{"):cleaned.rindex("}")+1]
    if cleaned.endswith("```"):
        cleaned = cleaned[:cleaned.rindex("}")+1]
    
    return cleaned


def _get_optimized_defaults():
    """返回优化后的参数默认值"""
    return {
        "reflection": {
            "batch_size": 8,
            "min_confidence": 0.52,  # .so 版可用更低阈值 + 二次校验
            ...
        }
    }
```

### 6.2 编译配置

```python
# setup.py
from Cython.Build import cythonize
from setuptools import setup, Extension

ext_modules = [
    Extension(
        "echomind.core._reflective_core",
        ["echomind/core/_reflective_core.pyx"],
    ),
]

setup(
    name="echomind",
    ext_modules=cythonize(ext_modules, language_level="3",
                          compiler_directives={
                              "binding": False,
                              "linetrace": False,
                          }),
)
```

### 6.3 编译命令

```bash
# 编译
cd /mnt/d/llm/echomind_memory.skill
python setup.py build_ext --inplace

# 产物示例
core/_reflective_core.cpython-311-x86_64-linux-gnu.so

# 验证
python -c "from core._reflective_core import _build_prompt; print('OK')"
```

### 6.4 多平台产物

```bash
# Linux x86_64 (Python 3.11)
core/_reflective_core.cpython-311-x86_64-linux-gnu.so

# macOS arm64
core/_reflective_core.cpython-311-darwin.so

# Windows x86_64
core/_reflective_core.cpython-311-win_amd64.pyd
```

### 6.5 条件加载实现

```python
# core/reflective_agent.py — 条件加载
import logging
logger = logging.getLogger("ReflectiveAgent")

_SO_LOADED = False
_build_prompt = None
_parse_result_advanced = None

try:
    from ._reflective_core import (
        _build_prompt as _so_build_prompt,
        _parse_result_advanced as _so_parse,
        _get_optimized_defaults as _so_defaults,
    )
    _build_prompt = _so_build_prompt
    _parse_result_advanced = _so_parse
    _SO_LOADED = True
    logger.info("ReflectiveAgent: protected mode (.so loaded)")
except ImportError:
    from ._reflective_fallback import (
        _build_prompt as _fb_build_prompt,
        _get_optimized_defaults as _fb_defaults,
    )
    _build_prompt = _fb_build_prompt
    _SO_LOADED = False
    logger.info("ReflectiveAgent: open-source mode (fallback)")
```

### 6.6 开源 Fallback

```python
# core/_reflective_fallback.py — 开源版简易实现
import string
from pathlib import Path

def _build_prompt(context: str, config: dict) -> str:
    """Fallback: 从 prompts/ 或代码内置"""
    prompt_dir = config.get("prompts_dir", "prompts")
    path = Path(prompt_dir) / "reflection_distill.txt"
    if path.exists():
        template = string.Template(path.read_text(encoding="utf-8"))
        return template.safe_substitute(context=context)
    return _inline_fallback(context)

def _get_optimized_defaults() -> dict:
    return {}

def _inline_fallback(context: str) -> str:
    return f"""Summarize these interactions and extract patterns:

{context}

Output JSON with fields: key_insights, user_preferences, procedural_rules, 
new_knowledge, forget_suggestions, confidence"""
```

### 6.7 `.gitignore` 配置

```gitignore
# .gitignore — 不要推送源文件
core/_reflective_core.pyx
core/_reflective_core.c

# 但接受编译产物
# core/_reflective_core.cpython-*.so
```

---

## 七、v1.0.10 ↔ v1.1.0 过渡机制

### 7.1 核心策略

**一套代码，条件加载，零分支维护**

```
v1.0.10         →  pip install echomind →    .so 不存在 →   fallback 模式
                                                    ↓
v1.1.0          →  pip install echomind →    .so 存在   →   保护模式
```

### 7.2 行为差异

| 功能 | v1.0.10 (fallback) | v1.1.0 (protected) |
|------|-------------------|-------------------|
| 反思 Prompt | 简单 f-string | 完整 + Few-Shot 注入 |
| JSON 解析 | `model_validate_json` | + .so 二次校验 |
| 默认参数 | 代码 fallback | Cython 优化值 |
| 领域检测 | YAML 配置 | YAML 配置 |
| 数据库 | 同 | 同 |
| API | 同 | 同 |
| **用户感知** | **无任何区别** | **无任何区别** |

### 7.3 版本检测（日志 + `_SO_LOADED`）

```python
# memory_agent.py 初始化
if self.reflective._SO_LOADED:
    logger.info("EchoMind v1.1.0 (protected reflection)")
else:
    logger.info("EchoMind v1.0.x (open-source reflection)")
```

### 7.4 版本标记

```python
# __init__.py
from core._reflective_core_loader import get_version_string

__version__ = get_version_string()
# v1.0.10 if fallback, v1.1.0 if protected
```

```python
# core/_reflective_core_loader.py
"""版本检测"""
from .reflective_agent import _SO_LOADED

def get_version_string() -> str:
    return "1.1.0" if _SO_LOADED else "1.0.10"
```

### 7.5 数据库兼容

**数据库结构无变化**：reflection 表 schema 相同。  
**迁移**：旧版本 SQLite 文件直接在 v1.1.0 打开，0 改动。

---

## 八、发布与安装

### 8.1 安装脚本

```bash
# install.sh — 一键安装
#!/bin/bash
set -e

SKILL_DIR="/mnt/d/llm/echomind_memory.skill"
INSTALL_DIR="$HOME/.hermes/skills/echomind-memory"
PLUGIN_DIR="$HOME/.hermes/plugins/echomind"
CONFIG_DIR="$HOME/.echomind"

echo "=== EchoMind v1.1.0 Install ==="

# 1. 编译 .so (如果 Cython 源文件存在)
if [ -f "$SKILL_DIR/core/_reflective_core.pyx" ]; then
    echo "  [1/5] Compiling .so..."
    cd "$SKILL_DIR"
    python setup.py build_ext --inplace || echo "  ⚠ .so compile skipped"
fi

# 2. 安装到 Hermes skill
echo "  [2/5] Installing to $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"
cp -r "$SKILL_DIR"/ "$INSTALL_DIR/"

# 3. 安装到 Hermes plugin (MemoryProvider)
echo "  [3/5] Installing to $PLUGIN_DIR..."
mkdir -p "$PLUGIN_DIR"
cp -r "$INSTALL_DIR"/ "$PLUGIN_DIR/"

# 4. 确保 .so 随同安装
if [ -f "$SKILL_DIR/core/_reflective_core.cpython-311-x86_64-linux-gnu.so" ]; then
    echo "  [4/5] Copying .so..."
    cp "$SKILL_DIR/core/_reflective_core.cpython-311-x86_64-linux-gnu.so" \
       "$INSTALL_DIR/core/"
    cp "$SKILL_DIR/core/_reflective_core.cpython-311-x86_64-linux-gnu.so" \
       "$PLUGIN_DIR/core/"
fi

# 5. 生成默认配置
if [ ! -f "$CONFIG_DIR/echomind_config.yaml" ]; then
    mkdir -p "$CONFIG_DIR"
    cp "$INSTALL_DIR/echomind_config.yaml" "$CONFIG_DIR/"
fi

echo "  [5/5] Done!"

# 验证
python -c "
from core.reflective_agent import _SO_LOADED
print(f'EchoMind: protected={_SO_LOADED}')
"
```

### 8.2 GitHub Release Assets

```yaml
# .github/release.yaml (手动)
assets:
  - echomind-v1.1.0.tar.gz                           # 纯 Python (fallback)
  - echomind-v1.1.0-linux-x86_64-cp311.whl           # Linux + .so
  - echomind-v1.1.0-linux-x86_64-cp312.whl
  - echomind-v1.1.0-macos-arm64-cp311.whl             # macOS + .so
  - echomind-v1.1.0-win-amd64-cp311.whl               # Win + .pyd
```

### 8.3 部署到多平台

```bash
# Hermes Agent → Provider
hermes config set memory.provider echomind

# OpenClaw → skill.yaml
pip install echomind
# main.py call() 自动可用

# OpenCode → memory tool
# (通过 HTTP API localhost:8005)
```

---

## 九、实施路线（6 Phase，12 小时）

### Phase 1: ConfigManager + YAML（2h）

| 文件 | 操作 | 行数 |
|------|------|------|
| `core/config_manager.py` | 新建 ConfigManager 类 | +150 |
| `echomind_config.yaml` | 新建全量配置文件 | +80 |

### Phase 2: Prompts 抽取（1h）

| 文件 | 操作 | 行数 |
|------|------|------|
| `prompts/reflection_distill.txt` | 新建 Prompt 文件 | +35 |
| `core/reflective_agent.py` | `_build_reflection_prompt` 改为委托 | +8/-20 |

### Phase 3: 硬编码参数迁移（3h）

| 文件 | 操作 | 行数 |
|------|------|------|
| `core/reflective_agent.py` | config dict → get_section | +5/-10 |
| `core/memory_agent.py` | RL, retrieval, domain, inference | +30/-25 |
| `core/learning/rl_weight_optimizer.py` | max_buffer_size | +5/-5 |
| `adapters/hermes_provider.py` | LLM URL + timeout | +10/-5 |
| `adapters/http_api.py` | port + host | +3/-3 |
| `main.py` | port → config | +3/-3 |
| `__init__.py` | 动态版本号 | +5/-0 |

### Phase 4: .so Cython（3h）

| 文件 | 操作 | 行数 |
|------|------|------|
| `core/_reflective_core.pyx` | Cython 源文件 | +200 |
| `core/_reflective_fallback.py` | 开源 fallback | +60 |
| `setup.py` | Cython 编译配置 | +20 |
| `core/reflective_agent.py` | 条件加载 try/except | +15/-0 |
| `core/_reflective_core_loader.py` | 版本检测 | +10 |

### Phase 5: 集成测试（2h）

| 测试 | 方式 |
|------|------|
| 有 .so 模式 | 编译后 pytest |
| 无 .so 模式 | 删除 .so → pytest |
| YAML 缺失 | 删除 YAML → 代码默认值兜底 |
| YAML 无效 | YAML parse error → 自动回退 |
| API 运行时覆盖 | POST /api/config/parameter → 验证 |

### Phase 6: 发布 + 安装（1h）

| 任务 | 文件 |
|------|------|
| install.sh | 一键安装 |
| GitHub Release | tar.gz + .whl |

---

## 十、附录

### 附录 A: 完整参数映射（37 项）

| 配置键 | 文件:行 | 旧值 | 来源 |
|--------|---------|------|------|
| rl.initial_weights.relevance | memory:271 | 0.4 | BM25 |
| rl.initial_weights.recency | memory:271 | 0.2 | Ebbinghaus |
| rl.initial_weights.frequency | memory:271 | 0.15 | 曝光效应 |
| rl.initial_weights.explicit_feedback | memory:272 | 0.15 | 显式反馈 |
| rl.initial_weights.trust_score | memory:272 | 0.10 | LLM 偏差 | 
| rl.learning_rate | memory:274 | 0.07 | RL 居中值 |
| rl.decay_factor | memory:274 | 0.97 | EMA 平滑 |
| rl.max_buffer_size | rl:32 | 50 | 50 条趋势 |
| reflection.batch_size | reflective:39 | 8 | Miller's Law |
| reflection.min_confidence | reflective:40 | 0.6 | 置信度校准 |
| reflection.max_daily | reflective:41 | 10 | 成本控制 |
| reflection.min_records | hermes:338 | 6 | 最少记录 |
| reflection.max_tokens | hermes:464 | 1500 | LLM 输出 |
| retrieval.experience_top_k | memory:426 | 5 | 经验覆盖率 |
| retrieval.experience_min_success_rate.initial | memory:430 | 0.7 | 初始 |
| retrieval.experience_min_success_rate.final | memory:680 | 0.6 | 后期 |
| retrieval.context_limit | memory:443 | 2 | 会话数 |
| retrieval.research_top_k | memory:439 | 5 | 研究论文 |
| retrieval.preference_score_boost | memory:468 | 0.2 | 偏好权重 |
| llm.host | hermes:459 | localhost | Hermes API |
| llm.port | hermes:459 | 9119 | Hermes API |
| llm.model | hermes:461 | local | 默认 |
| llm.temperature | hermes:463 | 0.3 | 精度 |
| llm.max_tokens | hermes:464 | 1500 | 输出 |
| llm.timeout | hermes:466 | 60 | HTTP |
| server.host | http_api:222 | 0.0.0.0 | 绑定 |
| server.port | http_api:222 | 8005 | 服务 |
| inference.min_occurrence | memory:645 | 2 | 频次 |
| domain.default | memory:412 | general | 兜底 |

### 附录 B: 领域关键词完整配置

```yaml
domain:
  default: "general"
  keywords:
    operations_research:
      zh: ["运筹学","线性规划","整数规划","网络优化","排队论","库存管理"]
      en: ["operations research","linear programming","integer programming",
           "network optimization","queuing theory","inventory management"]
    supply_chain:
      zh: ["供应链","物流","库存","仓储","配送","牛鞭效应"]
      en: ["supply chain","logistics","inventory","bullwhip effect"]
    decision_analysis:
      zh: ["决策分析","多准则","层次分析","AHP","ANP","TOPSIS"]
      en: ["decision analysis","MCDM","AHP","ANP","TOPSIS"]
    optimization:
      zh: ["优化","凸优化","梯度","遗传算法","粒子群","模拟退火"]
      en: ["optimization","convex","genetic algorithm","PSO","simulated annealing"]
    simulation:
      zh: ["仿真","模拟","蒙特卡洛","离散事件","系统动力学"]
      en: ["simulation","Monte Carlo","discrete event","system dynamics"]
    game_theory:
      zh: ["博弈","纳什均衡","拍卖","机制设计"]
      en: ["game theory","Nash equilibrium","auction","mechanism design"]
    forecasting:
      zh: ["预测","时间序列","ARIMA","Prophet","LSTM"]
      en: ["forecasting","time series","ARIMA","Prophet","LSTM"]
    project_management:
      zh: ["项目管理","关键路径","CMP","PERT","WBS"]
      en: ["project management","critical path","CMP","PERT","WBS"]
    queuing_theory:
      zh: ["排队论","M/M/1","Little定律","服务系统","到达率"]
      en: ["queuing theory","M/M/1","Little's law","service rate","arrival rate"]
```

### 附录 C: 改动量汇总

| 类别 | 文件 | 操作 | 行数 |
|------|------|------|------|
| 新增 | `core/config_manager.py` | 创建 | +170 |
| 新增 | `echomind_config.yaml` | 创建 | +90 |
| 新增 | `prompts/reflection_distill.txt` | 创建 | +35 |
| 新增 | `core/_reflective_core.pyx` | Cython 源 | +200 |
| 新增 | `core/_reflective_fallback.py` | 开源 fallback | +60 |
| 新增 | `setup.py` | 编译 | +20 |
| 新增 | `core/_reflective_core_loader.py` | 版本 | +10 |
| 新增 | `install.sh` | 安装 | +40 |
| 修改 | `core/reflective_agent.py` | 条件加载 | +15/-25 |
| 修改 | `core/memory_agent.py` | 参数 | +30/-25 |
| 修改 | `core/learning/rl_weight_optimizer.py` | 参数 | +5/-5 |
| 修改 | `adapters/hermes_provider.py` | 参数 | +10/-5 |
| 修改 | `adapters/http_api.py` | port | +3/-3 |
| 修改 | `main.py` | port | +3/-3 |
| 修改 | `__init__.py` | 版本 | +5/-0 |
| **总计** | | **净增 ~580 行** | |

### 附录 D: 安装验证

```bash
# 终端验证
$ hermes plugins list | grep echomind
✓ echomind v1.1.0 — exclusive plugin — activate via memory.provider config

# 日志验证
$ cat ~/.echomind/logs/*
EchoMind v1.1.0 (protected reflection)
Config loaded from ~/.echomind/echomind_config.yaml
SQLite persistence enabled (7 tables, 6 memory types loaded)

# API 验证
$ curl http://localhost:8005/health
{"status": "ok", "storage": "sqlite", "version": "1.1.0", "protected": true}
```

### 附录 E: 安全边界

| 风险 | 概率 | 缓解 |
|------|------|------|
| .so 与 Python 版本不兼容 | 中 | fallback 自动降级 |
| strings 提取 .so 中的 Prompt | 高 | Prompt 有动态 ${context} 插值，无上下文价值减半 |
| .so 反编译 | 低 | Cython → C → 汇编，ID Pro 需 4-8h |
| 用户升级后参数丢失 | 低 | install.sh 保留已有 YAML |
| 配置文件被误删 | 低 | ConfigManager 自动回退到代码默认 |