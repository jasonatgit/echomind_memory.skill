# EchoMind 可配置化方案 — Prompts + 参数 + 领域

> 2026-05-19 | v1.1.0 → v1.2.0 规划  
> 目标：将所有硬编码的 Prompt、算法参数、领域定义从代码中移出，统一由配置文件管理。

---

## 目录

1. Prompts 抽取
2. 算法参数配置化
3. 领域检测配置化（含 AI 领域实例）
4. API 端点动态扩展
5. 完整配置文件示例
6. 实施路线

---

## 一、Prompts 抽取

### 1.1 当前可抽取的 Prompt

项目中目前只有 **1 个完整的 LLM Prompt**，位于 `core/reflective_agent.py:164-197` 的 `_build_reflection_prompt()` 方法中。

**抽取方式**：使用 `.txt` 文件 + `string.Template`（Python 标准库，零依赖）。目录结构：

```
prompts/
  reflection_distill.txt           # P1: 反思蒸馏 Prompt（立即可做）
  reflection_refine.txt            # P2: 两阶段验证 Prompt（v1.2 实施）
  memory_tool_parse.txt            # P3: memory 工具解析 Prompt（未来）
  few_shot_examples.json           # Few-Shot 示例库
```

**P1 内容**（`prompts/reflection_distill.txt`）：

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
  "forget_suggestions": ["temporary test data from user vfy", ...],
  "confidence": 0.82
}

RULES:
- Extract GENERALIZABLE patterns, NOT specific code snippets
- User preferences: "key=value" format
- Procedural rules: "if CONDITION -> take ACTION" format
- Confidence: be HONEST — if little to extract, use low confidence (< 0.6)
```

**代码改造**（`core/reflective_agent.py`）：

```python
import string
from pathlib import Path

def _load_prompt(self, name: str) -> string.Template:
    prompt_dir = self.config.get("prompts_dir", "prompts")
    path = Path(prompt_dir) / f"{name}.txt"
    return string.Template(path.read_text(encoding="utf-8"))

def _build_reflection_prompt(self, context: str) -> str:
    template = self._load_prompt("reflection_distill")
    few_shot = self._build_few_shot_section(context)
    return template.safe_substitute(
        context=context,
        few_shot=few_shot,
    )
```

**P2 内容**（`prompts/reflection_refine.txt`，v1.2 实施）：

```text
You are the Refinement stage of EchoMind's Self-Reflective Agent.

Your task: Cross-validate the first-round reflection against existing 
knowledge and user preferences.

ROUND 1 OUTPUT:
${round1_output}

EXISTING KNOWLEDGE:
${existing_knowledge}

USER PREFERENCES:
${existing_preferences}

ORIGINAL EPISODIC RECORDS:
${context}

Output JSON with a "corrections" field listing any Round 1 errors:
{
  "corrections": ["Round 1 insight X contradicts existing knowledge Y", ...],
  "key_insights": [...],       // merged: keep valid, remove corrected
  "user_preferences": [...],
  "procedural_rules": [...],
  "new_knowledge": [...],
  "forget_suggestions": [...],
  "confidence": 0.85
}
```

---

## 二、算法参数配置化

### 2.1 参数分类与来源

#### A. RL 权重优化器（`rl_weight_optimizer.py`）

| 参数 | 当前硬编码值 | 来源依据 |
|------|------------|---------|
| `rl.initial_weights.relevance` | 0.40 | 信息检索 BM25 核心权重，与 LambdaMART 排名一致 |
| `rl.initial_weights.recency` | 0.20 | Ebbinghaus 遗忘曲线，20% 足以让新记忆超越旧记忆 |
| `rl.initial_weights.frequency` | 0.15 | 曝光效应（mere-exposure），但防短期重复会话虚高 |
| `rl.initial_weights.explicit_feedback` | 0.15 | 显式反馈是最强信号，但现实中极少出现 |
| `rl.initial_weights.trust_score` | 0.10 | LLM 自评置信度已知有系统偏差，设最低权重 |
| `rl.learning_rate` | 0.07 | 标准 RL 0.01-0.1 居中，10 次反馈调整 0.35 |
| `rl.decay_factor` | 0.97 | EMA 平滑系数，5 次前反馈权重衰减不足 5% |
| `rl.max_buffer_size` | 50 | 50 条反馈足以捕捉趋势，超出早期遗忘 |

#### B. 反思触发（`reflective_agent.py`+`memory_agent.py`）

| 参数 | 当前硬编码值 | 来源依据 |
|------|------------|---------|
| `reflection.batch_size` | 8 | Miller's Law (7±2)，8 次 store ~ 每小时 1 次反思 |
| `reflection.min_confidence` | 0.6 | LLM self-eval 偏差研究，0.6 ≈ 有效阈值 0.4 |
| `reflection.min_records` | 6 | 少于 6 条 Episodic 不足以提炼模式 |
| `reflection.max_daily` | 10 | 防止高频用户一天触发 50+ 次，控制成本 |
| `reflection.max_tokens` | 1500 | LLM 反思输出通常 500-1000 tokens，留余量 |

#### C. 检索参数（`memory_agent.py`）

| 参数 | 当前硬编码值 | 来源依据 |
|------|------------|---------|
| `retrieval.experience_top_k` | 5 | 前 5 条经验通常覆盖 90% 相关性 |
| `retrieval.experience_min_success_rate.initial` | 0.7 | 初始检索要求 70%+ 成功率 |
| `retrieval.experience_min_success_rate.final` | 0.6 | 后期放宽到 60%（更多候选） |
| `retrieval.experience_limit` | 5 | 同上 |
| `retrieval.research_top_k` | 5 | 同经验检索一致 |
| `retrieval.context_limit` | 2 | 最近 2 个会话足以恢复上下文 |
| `retrieval.preference_score_boost` | 0.2 | 用户偏好比普通 context 高 20% 优先级 |
| `retrieval.relevance_multiplier` | 0.6 | 默认检索 relevance 占 60% |
| `retrieval.recency_multiplier` | 0.5 | 默认检索 recency 占 50% |

#### D. 偏好推理（`memory_agent.py`）

| 参数 | 当前硬编码值 | 来源依据 |
|------|------------|---------|
| `inference.keywords.concise` | ["简短","简洁"] | 中文对话中最高频的"简洁"请求 |
| `inference.keywords.detailed` | ["type hint","Optional[str]"] | Python 类型注解的标志信号 |
| `inference.keywords.concise_code` | ["简洁","不要注释"] | 典型的"不要注释"风格要求 |
| `inference.min_occurrence` | 2 | 出现 2 次以上才认为是有意偏好，1 次可能是误读 |

---

## 三、领域检测配置化

### 3.1 当前问题

`_detect_research_domain()`（`memory_agent.py:397-412`）硬编码了 9 个管理科学领域的 keyword map。切换领域需改代码+重新部署。

### 3.2 配置文件方案

#### 管理科学与工程（当前默认配置）

```yaml
domain:
  default: "general"
  strategy: "keyword"    # keyword | embedding (v1.3)
  
  domains:
    operations_research:
      name: "运筹学"
      keywords:
        zh: ["运筹学","线性规划","整数规划","非线性规划","动态规划",
             "网络优化","排队论","库存管理","运输问题","指派问题",
             "目标规划","灵敏度分析","对偶理论","分支定界","割平面",
             "单纯形法","内点法"]
        en: ["operations research","linear programming","integer programming",
             "nonlinear programming","dynamic programming","network optimization",
             "queuing theory","inventory management","transportation problem",
             "simplex method","interior point"]

    supply_chain:
      name: "供应链管理"
      keywords:
        zh: ["供应链","物流","库存","仓储","配送","采购","供应商",
             "牛鞭效应","JIT","精益","看板","第三方物流","冷链",
             "跨境物流","最后一公里"]
        en: ["supply chain","logistics","inventory","warehouse","distribution",
             "procurement","vendor","bullwhip effect","JIT","lean","kanban",
             "3PL","cold chain","last mile"]

    optimization:
      name: "最优化方法"
      keywords:
        zh: ["优化","最优","凸优化","梯度下降","牛顿法","拉格朗日",
             "KKT条件","对偶","遗传算法","粒子群","模拟退火","蚁群",
             "启发式","元启发","全局优化","局部最优"]
        en: ["optimization","convex","gradient descent","Newton method",
             "Lagrangian","KKT","dual","genetic algorithm","PSO",
             "simulated annealing","ant colony","heuristic","metaheuristic"]

    simulation:
      name: "系统仿真"
      keywords:
        zh: ["仿真","模拟","蒙特卡洛","蒙特卡罗","离散事件","系统动力学",
             "agent建模","多智能体","元胞自动机","随机过程","马尔可夫"]
        en: ["simulation","Monte Carlo","discrete event","system dynamics",
             "agent-based","multi-agent","stochastic","Markov"]

    decision_analysis:
      name: "决策分析"
      keywords:
        zh: ["决策分析","多准则","多目标","层次分析","AHP","ANP",
             "TOPSIS","ELECTRE","风险分析","不确定性","灵敏度","稳健性"]
        en: ["decision analysis","multi-criteria","MCDM","AHP","ANP",
             "TOPSIS","risk analysis","uncertainty","sensitivity"]

    game_theory:
      name: "博弈论"
      keywords:
        zh: ["博弈","纳什均衡","零和","非零和","合作博弈","非合作博弈",
             "讨价还价","拍卖","机制设计","占优策略","囚徒困境"]
        en: ["game theory","Nash equilibrium","zero-sum","prisoner dilemma",
             "auction","mechanism design","bargaining"]

    forecasting:
      name: "预测与时间序列"
      keywords:
        zh: ["预测","时间序列","ARIMA","指数平滑","Holt-Winters",
             "季节性","趋势","回归","机器学习预测","LSTM预测","Prophet"]
        en: ["forecasting","time series","ARIMA","exponential smoothing",
             "seasonality","LSTM","Prophet","demand forecasting"]

    project_management:
      name: "项目管理"
      keywords:
        zh: ["项目管理","关键路径","CPM","PERT","甘特图","资源分配",
             "调度","进度","里程碑","WBS","挣值","PMBOK"]
        en: ["project management","critical path","CPM","PERT","Gantt",
             "resource allocation","scheduling","WBS","EVM"]

    queuing_theory:
      name: "排队论"
      keywords:
        zh: ["排队论","队列","M/M/1","M/M/c","服务系统","等待时间",
             "到达率","服务率","Little定律","生灭过程","呼叫中心"]
        en: ["queuing theory","queue","M/M/1","M/M/c","service system",
             "waiting time","Little's law","service rate"]

    data_science:
      name: "数据科学"
      keywords:
        zh: ["数据分析","统计","回归","分类","聚类","假设检验",
             "p值","置信区间","特征工程","pandas","numpy","scikit-learn"]
        en: ["data science","statistics","regression","classification",
             "clustering","hypothesis testing","p-value","machine learning"]
```

#### 切换到计算机科学（注释/取消注释）

```yaml
# domain:
#   domains:
#     software_engineering:
#       name: "软件工程"
#       keywords:
#         zh: ["软件工程","架构设计","微服务","DDD","SOLID","设计模式",
#              "重构","敏捷","Scrum","DevOps","CI/CD","TDD","代码审查",
#              "技术债务","面向对象","封装","继承","多态"]
#         en: ["software engineering","architecture","microservices",
#              "SOLID","design patterns","refactoring","agile","Scrum",
#              "DevOps","CI/CD","TDD","code review","technical debt","OOP"]
#     
#     systems:
#       name: "计算机系统"
#       keywords:
#         zh: ["操作系统","Linux","内核","文件系统","进程","线程","并发",
#              "锁","死锁","内存管理","虚拟内存","缓存","IO","网络栈",
#              "CPU调度","分页","分段"]
#         en: ["operating system","Linux","kernel","filesystem","process",
#              "thread","concurrency","lock","deadlock","memory management",
#              "virtual memory","cache","IO","scheduling"]
#     
#     database:
#       name: "数据库"
#       keywords:
#         zh: ["数据库","SQL","NoSQL","MySQL","PostgreSQL","SQLite","索引",
#              "事务","ACID","分库分表","读写分离","Redis","Elasticsearch",
#              "MongoDB","查询优化","ER图","范式"]
#         en: ["database","SQL","NoSQL","MySQL","PostgreSQL","SQLite","index",
#              "transaction","ACID","sharding","Redis","Elasticsearch",
#              "MongoDB","query optimization","normalization"]
#     
#     distributed:
#       name: "分布式系统"
#       keywords:
#         zh: ["分布式","一致性","Paxos","Raft","共识算法","CAP定理",
#              "微服务","Kubernetes","Docker","服务发现","负载均衡",
#              "容错","限流","熔断","gRPC","消息队列"]
#         en: ["distributed","consensus","Paxos","Raft","CAP theorem",
#              "microservices","Kubernetes","Docker","service discovery",
#              "load balancing","fault tolerance","rate limiting",
#              "circuit breaker","gRPC","message queue"]
#     
#     network:
#       name: "计算机网络"
#       keywords:
#         zh: ["网络","TCP/IP","HTTP","DNS","路由","交换机","子网",
#              "防火墙","VPN","CDN","WebSocket","QUIC","TLS","SSL"]
#         en: ["network","TCP/IP","HTTP","DNS","routing","switch","subnet",
#              "firewall","VPN","CDN","WebSocket","QUIC","TLS","SSL"]
#     
#     security:
#       name: "网络安全"
#       keywords:
#         zh: ["安全","加密","解密","RSA","AES","哈希","签名","证书",
#              "XSS","SQL注入","CSRF","零信任","渗透测试","漏洞","CVE",
#              "防火墙","WAF","认证","授权","OAuth","JWT"]
#         en: ["security","encryption","RSA","AES","hash","signature",
#              "certificate","XSS","SQL injection","zero trust","CVE",
#              "firewall","WAF","authentication","authorization","OAuth","JWT"]
```

#### 切换到生物学（注释/取消注释）

```yaml
# domain:
#   domains:
#     molecular_biology:
#       name: "分子生物学"
#       keywords:
#         zh: ["分子生物学","DNA","RNA","蛋白质","基因","转录","翻译",
#              "PCR","CRISPR","基因编辑","质粒","载体","克隆","表达",
#              "Northern blot","Western blot","电泳"]
#         en: ["molecular biology","DNA","RNA","protein","gene",
#              "transcription","translation","PCR","CRISPR","plasmid","clone",
#              "expression","Northern blot","Western blot","electrophoresis"]
#     
#     bioinformatics:
#       name: "生物信息学"
#       keywords:
#         zh: ["生物信息","序列比对","BLAST","基因组","转录组","蛋白组",
#              "NGS","RNA-seq","ChIP-seq","变异检测","系统发育","进化树",
#              "多序列比对","基因注释","通路分析"]
#         en: ["bioinformatics","sequence alignment","BLAST","genome",
#              "transcriptome","proteome","NGS","RNA-seq","phylogenetic",
#              "multiple sequence alignment","gene annotation","pathway"]
#     
#     cell_biology:
#       name: "细胞生物学"
#       keywords:
#         zh: ["细胞","线粒体","内质网","高尔基体","细胞膜","细胞核",
#              "信号通路","细胞周期","凋亡","自噬","干细胞","分化",
#              "细胞骨架","细胞外基质","受体"]
#         en: ["cell","mitochondria","ER","Golgi","membrane","nucleus",
#              "signaling pathway","cell cycle","apoptosis","autophagy",
#              "stem cell","differentiation","cytoskeleton","receptor"]
#     
#     neuroscience:
#       name: "神经科学"
#       keywords:
#         zh: ["神经","神经元","突触","神经递质","多巴胺","脑",
#              "电生理","脑电图","fMRI","认知","记忆","学习","意识",
#              "海马体","皮层","基底核"]
#         en: ["neural","neuron","synapse","neurotransmitter","dopamine",
#              "brain","EEG","fMRI","cognition","memory","learning",
#              "consciousness","hippocampus","cortex","basal ganglia"]
#     
#     genetics:
#       name: "遗传学"
#       keywords:
#         zh: ["遗传","基因","等位基因","显性","隐性","孟德尔","染色体",
#              "突变","多态性","表观遗传","甲基化","组蛋白修饰","非编码RNA"]
#         en: ["genetics","gene","allele","dominant","recessive","Mendel",
#              "chromosome","mutation","polymorphism","epigenetics",
#              "methylation","histone modification","non-coding RNA"]
```

### 3.3 AI 领域配置实例

```yaml
domain:
  default: "general"
  strategy: "keyword"
  
  ai:
    name: "人工智能"
    keywords:
      zh: ["人工智能","AI","机器学习","深度学习","神经网络",
           "监督学习","无监督学习","强化学习","迁移学习","联邦学习",
           "CNN","RNN","LSTM","Transformer","注意力机制","自注意力",
           "BERT","GPT","LLM","大语言模型","预训练","微调","SFT",
           "RLHF","DPO","PPO","GRPO","推理","蒸馏","量化","剪枝",
           "embedding","tokenizer","token","向量","RAG","Agent",
           "MCP","A2A","工具调用","function calling","prompt工程",
           "少样本","上下文学习","思维链","CoT","MoE","多模态"]
      en: ["artificial intelligence","AI","machine learning","deep learning",
           "neural network","supervised","unsupervised","reinforcement learning",
           "transfer learning","federated learning",
           "CNN","RNN","LSTM","Transformer","attention","self-attention",
           "BERT","GPT","LLM","large language model","pretraining",
           "fine-tuning","SFT","RLHF","DPO","PPO","GRPO",
           "inference","distillation","quantization","pruning",
           "embedding","tokenizer","RAG","Agent","MCP","A2A",
           "function calling","prompt engineering","few-shot",
           "in-context learning","chain of thought","CoT","MoE","multimodal"]

  computer_vision:
    name: "计算机视觉"
    keywords:
      zh: ["计算机视觉","图像识别","目标检测","图像分割","语义分割",
           "实例分割","YOLO","Faster R-CNN","Mask R-CNN","ViT",
           "图像生成","GAN","扩散模型","Stable Diffusion","VAE",
           "图像分类","物体检测","人脸识别","OCR","姿态估计",
           "三维重建","点云","NeRF","SLAM","超分辨率","图像增强"]
      en: ["computer vision","image recognition","object detection",
           "image segmentation","semantic segmentation","instance segmentation",
           "YOLO","Faster R-CNN","Mask R-CNN","ViT",
           "image generation","GAN","diffusion","Stable Diffusion","VAE",
           "image classification","face recognition","OCR","pose estimation",
           "3D reconstruction","point cloud","NeRF","SLAM","super resolution"]

  nlp:
    name: "自然语言处理"
    keywords:
      zh: ["自然语言处理","NLP","文本分类","命名实体识别","关系抽取",
           "文本生成","机器翻译","摘要","问答系统","文本理解",
           "情感分析","词向量","Word2Vec","GloVe","BERT",
           "序列标注","句法分析","语义角色标注","语料库","分词"]
      en: ["NLP","natural language processing","text classification",
           "named entity recognition","relation extraction",
           "text generation","machine translation","summarization",
           "question answering","sentiment analysis","word embedding",
           "Word2Vec","GloVe","BERT","sequence labeling","parsing",
           "semantic role labeling","corpus","tokenization"]

  speech_audio:
    name: "语音与音频"
    keywords:
      zh: ["语音识别","语音合成","ASR","TTS","Whisper","说话人识别",
           "声纹","音频分类","音乐生成","语音增强","语音分离",
           "端到端语音","WFST","CTC","RNN-T"]
      en: ["speech recognition","speech synthesis","ASR","TTS","Whisper",
           "speaker recognition","voiceprint","audio classification",
           "music generation","speech enhancement","speech separation",
           "end-to-end speech","CTC","RNN-T"]

  robotics:
    name: "机器人学"
    keywords:
      zh: ["机器人","ROS","路径规划","运动控制","机械臂","移动机器人",
           "SLAM","自主导航","抓取","操作","仿真","Gazebo"]
      en: ["robotics","ROS","path planning","motion control","manipulator",
           "mobile robot","SLAM","autonomous navigation","grasping",
           "manipulation","Gazebo"]

  recommendation:
    name: "推荐系统"
    keywords:
      zh: ["推荐系统","协同过滤","矩阵分解","内容推荐","序列推荐",
           "CTR预估","冷启动","召回","排序","多目标优化","图推荐"]
      en: ["recommendation","recommender","collaborative filtering",
           "matrix factorization","content-based","sequential recommendation",
           "CTR prediction","cold start","recall","ranking","multi-objective"]
```

---

## 四、API 端点动态扩展

通过 API 运行时修改领域或参数，无需重启服务。

### 4.1 `/api/config/domain` 领域 CRUD

#### GET `/api/config/domain`
**返回当前所有领域配置**

```
GET /api/config/domain

Response (200):
{
  "strategy": "keyword",
  "default": "general",
  "domains": {
    "optimization": {
      "name": "最优化方法",
      "keywords": {"zh": ["优化","凸优化",...], "en": ["optimization","convex",...]}
    },
    ...
    "ai": {
      "name": "人工智能",
      "keywords": {"zh": ["AI","机器学习","LLM",...], "en": ["AI","machine learning","LLM",...]}
    }
  }
}
```

#### POST `/api/config/domain`
**新增或覆盖领域**

```
POST /api/config/domain
Content-Type: application/json

{
  "domain_id": "reinforcement_learning",
  "domain": {
    "name": "强化学习",
    "keywords": {
      "zh": ["强化学习","RL","Q-learning","策略梯度","PPO","DQN","SAC",
             "TD3","马尔可夫决策过程","MDP","奖励","价值函数"],
      "en": ["reinforcement learning","RL","Q-learning","policy gradient",
             "PPO","DQN","SAC","TD3","MDP","reward","value function"]
    }
  }
}

Response (201):
{
  "status": "created",
  "domain_id": "reinforcement_learning",
  "mode": "memory"           // memory: 仅当前运行时生效
}
```

#### PUT `/api/config/domain/<domain_id>`
**更新已有领域的关键词**

```
PUT /api/config/domain/reinforcement_learning
Content-Type: application/json

{
  "name": "强化学习（修订）",
  "keywords": {"en": ["RL","reinforcement learning","Q-learning","PPO","MDP"]}
}

Response (200):
{
  "status": "updated",
  "domain_id": "reinforcement_learning",
  "mode": "memory"
}
```

#### DELETE `/api/config/domain/<domain_id>`
**删除领域**

```
DELETE /api/config/domain/<domain_id>

Response (200):
{
  "status": "deleted",
  "domain_id": "reinforcement_learning"
}
```

#### POST `/api/config/domain/persist`
**将运行时修改写入配置文件**

```
POST /api/config/domain/persist

Response (200):
{
  "status": "persisted",
  "config_path": "/home/jason/.echomind/echomind_config.yaml",
  "timestamp": "2026-05-19T10:30:00Z"
}
```

### 4.2 `/api/config/parameter` 参数运行时修改

#### GET `/api/config/parameter`
**查看所有可调参数和当前值**

```
GET /api/config/parameter

Response (200):
{
  "rl.learning_rate": {"value": 0.07, "range": [0.001, 0.2], "description": "RL 权重更新步长"},
  "reflection.batch_size": {"value": 8, "range": [3, 20], "description": "反思触发间隔（store 次数）"},
  "reflection.min_confidence": {"value": 0.6, "range": [0.1, 1.0], "description": "反思置信度阈值"},
  "retrieval.experience_top_k": {"value": 5, "range": [1, 20], "description": "经验检索 top-K"},
  "retrieval.context_limit": {"value": 2, "range": [1, 10], "description": "上下文恢复会话数"},
  "inference.min_occurrence": {"value": 2, "range": [1, 5], "description": "偏好推理最低出现次数"}
}
```

#### PUT `/api/config/parameter/<name>`
**修改单个参数**

```
PUT /api/config/parameter/reflection.batch_size
Content-Type: application/json

{
  "value": 12,
  "reason": "高频用户，减少反思频率"
}

Response (200):
{
  "status": "updated",
  "parameter": "reflection.batch_size",
  "old_value": 8,
  "new_value": 12,
  "effective": "immediate",
  "mode": "memory"        // memory: 仅运行时
}
```

#### POST `/api/config/parameter/validate`
**参数校验 — 不改动，只验证**

```
POST /api/config/parameter/validate
Content-Type: application/json

{
  "reflection.batch_size": 12,
  "reflection.min_confidence": 0.3
}

Response (200):
{
  "valid": false,
  "issues": [
    {"parameter": "reflection.min_confidence", "reason": "value 0.3 below minimum 0.6"}
  ]
}
```

### 4.3 运行时 vs 持久化策略

```
运行时修改（memory mode）
┌─────────┐    PUT /api/config/parameter     ┌──────────┐
│  API   │ ────────────────────────────────→ │  dict    │
│  call  │ ←────────────────────────────────  │  in RAM  │
└─────────┘    200 + effective: immediate    └──────────┘
                                                   │
                                                   │ POST /api/config/domain/persist
                                                   ▼
                                           ┌────────────────┐
                                           │  echomind_config.yaml │
                                           │  (YAML on disk)       │
                                           └────────────────┘

下次启动: 从配置文件 + 上次 API 修改合并
```

### 4.4 代码改造

```python
# core/config_api_manager.py
class ConfigApiManager:
    def __init__(self, config_path: str, runtime_config: dict):
        self.config_path = config_path
        self.runtime_overrides = {}
        self.parameters = {
            "reflection.batch_size": {"value": 8, "range": [3, 20]},
            "reflection.min_confidence": {"value": 0.6, "range": [0.1, 1.0]},
            # ... 完整列表从 echomind_config.yaml 加载
        }
    
    def get_parameter(self, name: str) -> dict:
        base = self.parameters.get(name)
        override = self.runtime_overrides.get(name)
        if override:
            return {**base, "value": override["value"], "source": "runtime"}
        return {**base, "source": "config"}
    
    def set_parameter(self, name: str, value, reason: str) -> dict:
        # 校验 range
        param = self.parameters.get(name)
        min_v, max_v = param.get("range", [0, float("inf")])
        if value < min_v or value > max_v:
            return {"status": "validation_error", "message": f"{name} must be in [{min_v}, {max_v}]"}
        old = param["value"]
        self.runtime_overrides[name] = {"value": value, "reason": reason}
        return {"status": "updated", "parameter": name, "old_value": old, "new_value": value}
    
    def persist(self) -> dict:
        # 将 runtime_overrides 合并到 YAML 文件
        ...

    def manage_domain(self, action: str, domain_id: str = None, data: dict = None) -> dict:
        """
        领域管理，参数：
        - action: "list" | "get" | "add" | "update" | "delete" | "persist"
        - domain_id: 领域ID (list 不需要)
        - data: domain dict {name, keywords} (add/update 需要)
        """
        if action == "list":
            return {"domains": self._get_all_domains()}
        elif action == "get":
            domain = self._get_domain(domain_id)
            if not domain:
                return {"status": 404, "message": f"Domain {domain_id} not found"}
            return domain
        elif action == "add":
            if domain_id in self._get_all_domains():
                return {"status": 409, "message": f"Domain {domain_id} already exists, use update"}
            self._set_domain(domain_id, data)
            return {"status": "created", "domain_id": domain_id}
        elif action == "update":
            if domain_id not in self._get_all_domains():
                return {"status": 404, "message": f"Domain {domain_id} not found, use add"}
            self._set_domain(domain_id, data)
            return {"status": "updated", "domain_id": domain_id}
        elif action == "delete":
            self._delete_domain(domain_id)
            return {"status": "deleted", "domain_id": domain_id}
```

### 4.5 FastAPI 集成

```python
# adapters/http_api.py — 新增端点

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/config")

class DomainData(BaseModel):
    name: str
    keywords: dict = Field(..., description="{'zh': [...], 'en': [...]}")

class ParameterData(BaseModel):
    value: float | int
    reason: str = ""

# === 领域 ===
@router.get("/domain")
def list_domains():
    return memory_agent.config_api.manage_domain("list")

@router.get("/domain/{domain_id}")
def get_domain(domain_id: str):
    return memory_agent.config_api.manage_domain("get", domain_id=domain_id)

@router.post("/domain/{domain_id}", status_code=201)
def add_domain(domain_id: str, data: DomainData):
    return memory_agent.config_api.manage_domain("add", domain_id, data.model_dump())

@router.put("/domain/{domain_id}")
def update_domain(domain_id: str, data: DomainData):
    return memory_agent.config_api.manage_domain("update", domain_id, data.model_dump())

@router.delete("/domain/{domain_id}")
def delete_domain(domain_id: str):
    return memory_agent.config_api.manage_domain("delete", domain_id=domain_id)

@router.post("/domain/persist")
def persist_domains():
    return memory_agent.config_api.manage_domain("persist")

# === 参数 ===
@router.get("/parameter")
def list_parameters():
    return memory_agent.config_api.get_all_parameters()

@router.get("/parameter/{name}")
def get_parameter(name: str):
    return memory_agent.config_api.get_parameter(name)

@router.put("/parameter/{name}")
def set_parameter(name: str, data: ParameterData):
    return memory_agent.config_api.set_parameter(name, data.value, data.reason)

@router.post("/parameter/validate")
def validate_parameters(data: dict):
    return memory_agent.config_api.validate_batch(data)
```

---

## 五、完整配置文件示例

```yaml
# echomind_config.yaml — EchoMind 全量可配置参数
# 位置：~/.echomind/echomind_config.yaml
# 用法：服务启动时读取，运行时通过 API 修改

# ── 通用设置 ──
prompts_dir: "prompts"
config_version: 2

# ── RL 权重优化器 ──
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

# ── 反思系统 ──
reflection:
  batch_size: 8
  min_confidence: 0.6
  min_records: 6
  max_daily: 10
  max_tokens: 1500
  max_rounds: 1               # 1=单次, 2=两阶段Distill+Refine(v1.2)
  adaptive_batch: true        # true=根据活跃度动态调整batch_size

# ── 检索参数 ──
retrieval:
  experience_top_k: 5
  experience_min_success_rate:
    initial: 0.7
    final: 0.6
  experience_limit: 5
  research_top_k: 5
  context_limit: 2
  preference_score_boost: 0.2
  dedup_threshold: 0.95       # cosine_sim > 0.95 判定为重复(v1.2)
  decay_lambda: 0.01          # Ebbinghaus 遗忘 λ(v1.2)

# ── 偏好推理 ──
inference:
  min_occurrence: 2
  strategy: "keyword"         # "keyword" | "llm" (v1.3)

# ── 领域检测 ──
domain:
  default: "general"
  strategy: "keyword"
```

---

## 六、实施路线

### Phase 1（v1.2.0-alpha）— + 1 个工作日

| 任务 | 改动量 | 优先级 |
|------|--------|--------|
| 创建 `echomind_config.yaml` | 1 个 YAML 文件 | P0 |
| 将 RL 权重/learning_rate/decay_factor 从代码移到 yaml | ~20 行 | P0 |
| 将反思 batch_size/min_confidence/max_daily 移到 yaml | ~15 行 | P0 |
| 将检索 top_k/limit/success_rate 移到 yaml | ~20 行 | P0 |
| 创建 `prompts/reflection_distill.txt` | 1 个 txt 文件 | P0 |
| 改造 `_build_reflection_prompt()` 使用 string.Template | ~15 行 | P0 |

### Phase 2（v1.2.0-beta）— + 2 个工作日

| 任务 | 改动量 | 优先级 |
|------|--------|--------|
| 领域 keyword map 从代码移到 yaml | ~30 行 | P1 |
| 创建 AI 领域 + 计算机视觉 + NLP + 语音 + 机器人 + 推荐 6 个 AI 子领域 | 1 个 yaml 段 | P1 |
| 添加 `/api/config/domain/*` 端点 | ~60 行 | P1 |
| 添加 `/api/config/parameter/*` 端点 | ~50 行 | P1 |
| `ConfigApiManager` 类实现 | ~100 行 | P1 |

### Phase 3（v1.2.0-rc）— + 1 个工作日

| 任务 | 改动量 | 优先级 |
|------|--------|--------|
| persist 功能（runtime → yaml）| ~30 行 | P2 |
| 参数 range 校验 + validate 端点 | ~20 行 | P2 |
| 领域切换时自动重载 domain_map | ~10 行 | P2 |

### 总改动量

```
+ 1 个 YAML 配置文件 (~60 行)
+ 3 个 Prompt txt 文件 (~70 行)
+ 1 个 config_api_manager.py (~100 行)
+ ~30 行 http_api.py 端点
- ~50 行 memory_agent.py/reflective_agent.py 硬编码
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
净新增 = ~210 行
```



---

## 附录 A: 参数值范围速查

| 参数 | 最小值 | 推荐值 | 最大值 | 单位 |
|------|--------|--------|--------|------|
| rl.learning_rate | 0.001 | 0.07 | 0.2 | — |
| rl.decay_factor | 0.8 | 0.97 | 0.999 | — |
| reflection.batch_size | 3 | 8 | 20 | store 次数 |
| reflection.min_confidence | 0.1 | 0.6 | 1.0 | — |
| reflection.max_daily | 1 | 10 | 50 | 次/天 |
| retrieval.experience_top_k | 1 | 5 | 20 | 条 |
| retrieval.context_limit | 1 | 2 | 10 | 会话 |
| inference.min_occurrence | 1 | 2 | 5 | 次 |

---

## 附录 B: 配置文件加载顺序

```
1. 默认值 (代码中的 DEFAULT_CONFIG dict)
   ↓
2. echomind_config.yaml (磁盘)
   ↓
3. API 运行时修改 (RAM overrides)
   ↓
4. _detect_research_domain() / RLWeightOptimizer / reflection 读取
```

优先级: `API overrides > YAML > 代码默认`