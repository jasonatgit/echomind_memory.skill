# EchoMind: RL Self-Learning Memory System

> This article explores EchoMind's RL (Reinforcement Learning) self-learning mechanism — from the five-dimensional weight model to advantage learning strategies, from user feedback loops to policy drift protection.
>
> Author: EchoMind Team  
> Date: June 2026

---

## 1. The Core Problem: Retrieval is Not Trivial

A memory system stores hundreds or thousands of entries. When a user asks a question, the system must decide: which memories are most worth retrieving? What order should they be presented? Which should be skipped entirely?

This is not a trivial sorting problem. Relevance, recency, and reliability are constantly in tension. A highly relevant memory from six months ago versus a moderately relevant memory from yesterday — which should rank higher?

The answer isn't universal. It depends on the user, the scenario, and the type of task. A researcher may value relevance over recency; a developer fixing a recent bug may value recency above all.

**A static ranking formula cannot simultaneously serve all scenarios. Ranking must self-adapt.**

---

## 2. The Five-Dimensional Weight Model

EchoMind decomposes the memory retrieval problem into five dimensions, each with an independent weight:

| Weight | Meaning | What it Gates |
|--------|---------|---------------|
| **relevance** | Content similarity between memory and query | How many keywords match? Does semantic meaning align? |
| **recency** | Time elapsed since memory was created/last accessed | Is this memory still fresh? |
| **frequency** | How often this memory has been retrieved | Is it frequently useful? |
| **explicit_feedback** | Whether the user has marked this memory as helpful | Has the user confirmed it? |
| **trust_score** | The memory's own reliability | How confident are we about its accuracy? |

The final importance score for each memory entry is:

> importance = f(relevance × w₁ + recency × w₂ + frequency × w₃ + feedback × w₄ + trust × w₅)

The challenge is: **what should w₁ through w₅ be?**

---

## 3. RL Feedback Loop: Learning From Users

### 3.1 The Basic Signal

Every user action generates an implicit or explicit signal:

- **Positive**: The user explicitly says "thanks" / "that worked" / gives positive feedback, or implicitly uses the retrieved memory successfully
- **Negative**: The user explicitly corrects the AI / says "no" / marks as unhelpful, or the retrieved memory leads to a wrong answer

These signals form the foundation of the RL reward: positive = +1, negative = -1.

### 3.2 The Update Mechanism

When feedback accumulates (every ~10 feedback records), EchoMind performs a weight update:

1. **Compute advantage**: `advantage = reward - baseline`
   - Baseline is the weighted average of recent rewards (last 20 entries, linear recency weighting)
   - This subtracts the "expected reward" from the raw reward — stabilizing the learning signal

2. **Predict current score**: using current weights, predict the expected reward

3. **Update weights**: `delta = learning_rate × (advantage - predicted) × state_features`
   - Cosine learning rate decay ensures stable convergence: lr decreases smoothly from initial to minimum over time

4. **Softmax normalization**: weights are renormalized via softmax to maintain a valid probability distribution

### 3.3 Advantage Baseline: Why It Matters

Without advantage baseline, every positive feedback adds +1 weight to all retrieved sources, regardless of context. If a user frequently uses the same type of query, all five weights drift upward together, and the system becomes unable to differentiate.

With advantage baseline, when the system's average performance is already good (baseline ~0.7), a +1 positive feedback yields advantage = 1.0 - 0.7 = 0.3 — a smaller update, rewarding only the marginal improvement. Conversely, during a rough patch (baseline ~0.2), a +1 feedback yields advantage = 1.0 - 0.2 = 0.8 — a much stronger correction signal.

---

## 4. Exploration vs. Exploitation

### 4.1 Epsilon-Greedy Exploration

Pure exploitation (always using the current best weights) risks falling into local optima. EchoMind uses epsilon-greedy exploration:

- With probability ε (decaying from 0.1 to 0.01 over time), randomly perturb a single weight
- With probability 1-ε, use the current learned weights

This ensures the system occasionally tries new weight combinations to discover better configurations.

### 4.2 RCW: Reward Contribution Weighting

When multiple memory sources are retrieved together, how is reward distributed among them? Giving equal reward to all is unfair — a highly relevant source and an irrelevant one get the same signal.

RCW computes per-source contribution weights:

- For each retrieved memory source (user, knowledge, experience, etc.), compute `relevance × trust_score`
- Normalize across all sources to sum to 1.0
- Apply the reward proportionally to each source's contribution

This means: sources with higher relevance and trust get stronger weight updates, while low-quality sources receive minimal adjustments.

---

## 5. Policy Drift Protection

### 5.1 KPop: Divergence-Aware Decay

When the system's policy (weight distribution) has shifted significantly from a previous checkpoint, older memories may no longer be aligned with the new policy. EchoMind monitors this via:

- **Policy snapshots**: recorded every 100 feedbacks
- **Bidirectional KL divergence**: measured between current policy and the most recent snapshot

When divergence exceeds a threshold (default 2.0 nats), the `decay_all()` mechanism applies extra weight decay — effectively reducing the influence of older, policy-misaligned memories on the current ranking.

### 5.2 IcePop: Per-Feedback Learning Rate Adjustment

When a feedback record was generated under a significantly different weight configuration from the current one, its signal reliability is reduced. IcePop checks:

- Whether >80% of weight dimensions remain within [0.5×, 2.0×] of their snapshot values
- If not, reduce the learning rate for that feedback's weight update (minimum 30%)

This prevents feedback generated under drastically different policies from disrupting the current, well-tuned policy.

---

## 6. Formula Summary

**Advantage:**

> advantage = reward - baseline, where baseline = weighted_avg(recent_20_rewards)

**Weight Update:**

> w_new = w + lr × (advantage - predicted_score) × state_features

**Cosine Learning Rate Decay:**

> lr(t) = lr_min + (lr_base - lr_min) × 0.5 × (1 + cos(π × t / T))

**Epsilon-Greedy:**

> ε(t) = max(0.01, 0.1 - 0.09 × t / 500)

**RCW Contribution:**

> contribution_per_source = (relevance × trust) / Σ(relevance × trust)

**KPop Divergence:**

> extra_decay = min(0.3, (KL_div - 2.0) × 0.05)

---

## 7. Comparison with Other Approaches

| Dimension | EchoMind RL | Static Weights | Simple Feedback Counting | Full DRL |
|-----------|-------------|----------------|-------------------------|----------|
| Adaptivity | ✅ Self-adapting via feedback | ❌ Fixed | ⚠️ Simple accumulation | ✅ Full |
| Training cost | Low (batch updates) | None | Low | High (trajectory-level) |
| Convergence speed | Fast (cosine decay) | N/A | Slow | Variable |
| Exploration | ✅ Epsilon-greedy | ❌ | ❌ | ✅ Complex |
| Drift protection | ✅ KPop + IcePop | ❌ | ❌ | ⚠️ Depends |
| Infrastructure needed | Single Python process | N/A | N/A | GPU cluster |

The key design choice: EchoMind's RL is **lightweight enough** to run inside a single Python process alongside the agent, yet **sophisticated enough** to self-adapt across usage patterns. It doesn't require a separate training pipeline.

---

## 8. Conclusion

Traditional search systems use static ranking formulas written once and never updated. EchoMind's RL system learns: from every "thank you" and every "no," from which memories work and which don't, from adaptation to different users and scenarios.

The result: a memory system that gets better the more it's used. Not because the model improves, but because the retrieval strategy self-optimizes.

This self-learning capability, combined with the reflection engine and knowledge evolution mechanisms (explored in other articles in this series), forms EchoMind's complete memory intelligence stack.

---

> **This Series:**  
> Part 1: [Echomind:  Why Every AI Agent Needs a Memory System](echomind-agent-memory-article-en.md)  
> Part 2: Echomind:  RL Self-Learning Memory System (this article)  
> Part 3 (A): [Echomind:  Self-Reflective Agent — Reflection Engine and Memory Lifecycle](echomind-reflective-agent-part1-article-en.md)  
> Part 3 (B): [Echomind:  Self-Reflective Agent — Knowledge Evolution and Memory Governance](echomind-reflective-agent-part2-article-en.md)