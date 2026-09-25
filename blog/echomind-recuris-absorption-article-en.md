# EchoMind × Recuris: Teaching Memory to Attribute, Not Just Summarize

> How a recursive memory-evolution paper from NUS/Stanford/Oxford/Princeton shaped EchoMind v1.2.19: structured retrieval traces, component-attributed reflection, a fingerprint gate against decode noise, and a paired bootstrap gate for knowledge updates — with the math, the evidence, and what each piece buys the user.
>
> Author: EchoMind Team
> Date: September 2026

---

## 1. The Problem: Reflection That Summarizes Instead of Locates

### 1.1 What reflection does today — and why it isn't enough

EchoMind's reflection engine reads episodic records (what happened, turn by turn) and distills long-term knowledge. When a run of interactions goes badly, it produces insights like *"the user prefers concise responses"* — a **summary**. A summary is not useless, but it answers a different question than the one that matters when something breaks.

The question that matters is: **which part of the memory system should change?**

Consider a concrete failure. An agent session ends with the user unsatisfied. Under the hood, exactly one of these four diseases is present:

| Disease | Component | What actually happened | Correct repair |
|---|---|---|---|
| **Knowledge missing** | E (experiential) | The fact was never stored — no card, no entry | Write the knowledge |
| **Knowledge never invoked** | ρ (invocation policy) | It exists, but the retrieval key/timing missed it | Fix retrieval timing or keys |
| **Task state wrong** | W (working state) | The tracker recorded a completion that never happened | Fix the state or its grounding |
| **Discipline escaped** | C (checkers) | Progress was claimed without evidence | Tighten a completion predicate |

All four produce **the same observable**: a bad outcome. All four require **a different repair**. A summary collapses them into a single "this went badly" signal and leaves the repair to guesswork — and guessing wrong means the next session repeats the failure while the memory system accumulates entries that don't help.

### 1.2 The receipt: localization accuracy, measured

A paper from NUS, Stanford, Oxford and Princeton — *Recursive Experiential–Working Memory Evolution for Long-Horizon Agent Harnesses* (Recuris, arXiv:2608.24876) — put a number on this collapse. Their system records a **structured execution trace** linking every action to the state that triggered skill retrieval and the evidence used to accept or reject a state change:

```
Γ = ( x, { w_t, E_t, a_t, o_t, w̃_{t+1}, c_t, w_{t+1} }_{t=1..L}, y )
```

Reading the tuple left to right:

- `x` — the task instruction
- `w_t` — the **verified working state** at step `t` (what is done, what remains)
- `E_t` — the **experience/skills invoked** at step `t`
- `a_t`, `o_t` — the action and the environment observation
- `w̃_{t+1}` — the **proposed** next state (before verification)
- `c_t` — the **checker decisions** (which proposed transitions were accepted)
- `w_{t+1}` — the **committed** next state
- `y` — the final outcome

The trace's value shows up when you try to localize a failure to a component:

| Evidence available to the diagnoser | Localization accuracy |
|---|---|
| Final task outcome `y` alone | **13.0%** |
| Raw trajectory `{(a_t, o_t)}` | 37.0% |
| **Structured trace `Γ`** | **64.8%** |

The jump from 13.0% to 64.8% is not incremental — it is the difference between a system that can act on a failure and one that can only report it. **Without a trace, roughly four times out of five the system cannot say which component to repair.** Why? Because two of the four diseases are *non-events*: "knowledge that should have been invoked but wasn't" leaves no trace in a raw transcript — there is simply nothing where the retrieval should have been. Only a structured record of *what state existed at the moment of invocation* makes the absence visible.

### 1.3 Why the memory *state* matters more than the memory *content*

The paper's ablation is blunt about where the value lives. Measuring task success while adding memory components one at a time:

```
Δ(E only)   = +2.0 points     # add the skill cards, nothing else
Δ(W + ρ)    = +23.9 points    # add the verified state and the invocation policy
```

The machinery that decides **when** to invoke is worth an order of magnitude more than the content being invoked. The content is table stakes; the **grounded state** is the product. This is the single most important lesson EchoMind took from Recuris, because it reframes what a memory system should optimize: not "store more," but "know the current situation well enough to use what you stored."

EchoMind is a memory engine, not an execution harness: it does not drive the agent, so it cannot manufacture a working state from tool receipts the way Recuris does. What it *can* do is make retrieval **observable** (the trace) and make failures **attributable** (the reflection fields) — the two preconditions for ever closing the loop on state.

---

## 2. What Recuris Does Differently

Recuris evolves a frozen agent's **Skill Memory** `M = (E, W, ρ, C)` instead of its weights or its prompt. The agent is untouched; only the external memory-control layer changes:

- **E** — experiential memory: skill cards distilled from failures (the same idea as EchoMind's `knowledge_memory` / `experience_memory`)
- **W** — working memory: an evidence-verified task-state ledger, where an entry advances to `DONE` only when a real tool receipt grounds it
- **ρ** — invocation policy: which cards are delivered at which execution events, conditioned on the current working state
- **C** — checkers: completion predicates that must hold before progress is claimed

Two nested loops make it recursive. **Within a task**, the working state guides skill invocation; after execution, verified feedback updates the state. **Across tasks**, a fixed meta-agent reads the structured traces of failed runs, attributes each failure to exactly one component, patches exactly that component, and a **validation gate** admits the patch only on paired held-out evidence. The gate is pure arithmetic — no model votes on its own patch.

Three findings from the paper shaped our absorption choices:

1. **State-grounded invocation beats content retrieval.** Retrieving from the initial instruction or the full chat history degrades as the history grows; retrieving from a compact, verified state does not.
2. **Structured evidence enables targeted repair.** Because the trace records the state, the invoked skill, the action, and the checks, a failure can be localized to a component — and a component-scoped patch is far safer than a rewrite.
3. **Weak evidence must abstain, not reject.** Their gate admits a patch only when a paired bootstrap confidence interval excludes zero *and* regressions stay within a cap; when the evidence can't resolve the question, the gate abstains — because a statistically underpowered "no" is not a real no.

---

## 3. The Positioning Question: Harness vs Memory Engine

Recuris is an **agent harness** — it drives execution, sees tool receipts, replays environments. EchoMind is a **memory engine** — it does not drive the agent; it stores, ranks, and returns memory. That difference is decisive for what transfers:

| Recuris mechanism | Applies to EchoMind? | Reasoning |
|---|---|---|
| Structured execution trace | ✅ Yes | Retrieval already computes the raw material; it just wasn't recorded |
| Component-attributed reflection | ✅ Yes | EchoMind's 6 sub-agents are a natural, stable patch space |
| Fingerprint ("read the mechanism before the score") | ✅ Yes | `hit_history` already records the mechanism; it just wasn't enforced |
| Paired bootstrap validation gate | ✅ Yes | Rebuilt on `hit_history` / entry observability instead of environment replay |
| Verified working state (intent ledger) | ⚠️ Partial | A memory engine has no tool-receipt channel; the state can only be as grounded as the caller's evidence |
| Task-state-conditioned invocation | ⚠️ Partial | There is no *live* execution state to condition on; a recorded task list is a weaker signal |
| Status board / truth guard / domain oracles | ❌ No | These intercept an agent's draft messages and verify tool receipts; EchoMind has no drafts to intercept |
| Per-domain hand-written matchers | ❌ No | There is no environment replay to bind match keys against |

We ranked every candidate by one rule: **solve a proven EchoMind pain point, at proportionate cost, with prerequisites in place.** The paper's own ablations guided the ranking — components its experiments showed to be redundant were discounted:

- **E alone carries little** (+2.0): skill content without state-grounded invocation doesn't move the needle, so we prioritized the trace and attribution over "store more cards."
- **The truth guard's post-hoc audit was inert**: it rejected 172 unsupported completion claims with zero measurable effect, because by the time the audit runs, the action has already changed the environment. A guard that can only complain after the fact is not worth porting.

---

## 4. What Landed in v1.2.19: The Top Four

### 4.1 Structured Retrieval Trace (migration v12)

**The problem it solves.** Today, when a memory lookup returns nothing useful, there is no durable record of *what was asked, what candidates existed, and what was ranked where*. Debugging memory behavior means re-reading the conversation and guessing. Recuris's 13% figure is the cost of exactly this blindness.

**What was built.** Every `retrieve_for_task` now persists a `trace-v1` record onto the session's context row:

```json
{
  "schema": "trace-v1",
  "query": "python refactor",
  "retrieved": [
    {"id": "k:482...", "source": "knowledge", "importance": 0.78},
    {"id": "exp:91...", "source": "experience", "importance": 0.61},
    {"id": "ctx:sessA", "source": "context", "importance": 0.40}
  ],
  "retrieved_counts_by_source": {"knowledge": 3, "experience": 2, "context": 1},
  "top_n": 3,
  "captured_at": "2026-09-25T08:00:00+00:00"
}
```

The assembly **reuses the aggregated retrieval dictionary** that scoring already builds — there is no second query, no extra scan, and no new model call. A companion `save_context_trace` updates just the trace column without rewriting the (potentially large) message payload. Legacy rows keep `trace='{}'` and behave exactly as before.

**Why the numbers in the trace are trustworthy.** The `importance` values are not a summary computed after the fact — they are the exact scores the ranking used, produced by the unified scoring contract:

```
freshness(record) = 2^( -Δdays / half_life )          # Ebbinghaus decay, half_life = 69 days
base  = Σ(value_i × weight_i) / Σ(weight_i)           # per-source normalized base ∈ [0,1]
score = base × freshness × soft(origin)               # single recency lever + cross-origin penalty
```

Concretely, for a knowledge entry the base combines content relevance and trust under the RL weights; for an experience entry it additionally folds in a log-scaled frequency term:

```
knowledge:  base = (relevance·w_rel + trust·w_trust) / (w_rel + w_trust)
experience: freq_n = min(1, log1p(freq)/log1p(20))
            base = (rel·w_rel + freq_n·w_freq + trust·w_trust) / (w_rel + w_freq + w_trust)
```

Because every factor is either stored on the record or read from the current weight vector, **any trace can be re-derived exactly** from the database at any later time. The trace is evidence, not narration.

**Depth note — why a separate column.** The trace could have lived inside `messages`, but that would (a) bloat the conversation payload, (b) couple the evidence to message rewrites, and (c) make querying "show me retrievals where the top result had importance < 0.3" awkward. A dedicated column keeps the evidence first-class and queryable while leaving the transcript semantics untouched.

### 4.2 Component-Attributed Reflection

**The problem it solves.** A reflection that says "this went badly" gives you no repair target. Recuris localizes to one of four components; EchoMind's equivalent is one of its six memory types plus an explicit "can't attribute" state.

**What was built.** `ReflectionOutput` gains two fields:

- **`primary_owner`** — the memory component this reflection attributes its findings to: `knowledge | experience | task | context | user | research | none`
- **`failure_type`** — `knowledge_gap` (the knowledge was missing) or `invocation_miss` (it existed but was never retrieved in time)

Both default to `""` (not attributed), so older LLM outputs and third-party callers are entirely unaffected. The English and Chinese reflection prompts now request the attribution with an explicit **abstention rule**: *never convert ambiguity into an attribution — use "none" when unsure.* That rule is lifted directly from Recuris's diagnosis protocol, where proposing nothing (`fixes: []`) is a first-class outcome rather than a failure.

**The formal shape of the repair decision.** The attribution is the argmax of a localization posterior over components:

```
attribution(Γ) = argmax_{c ∈ {E,W,ρ,C}}  P( component c requires repair | Γ )
```

We do not pretend to estimate that posterior with a model — that would be exactly the kind of overconfident guess the abstention rule forbids. Instead, the reflection emits a **discrete** attribution with an explicit abstention state, and only attributed findings become eligible for component-scoped actions. The mapping from EchoMind components to EchoMind memory types is direct:

| Attribution | EchoMind target | Typical repair |
|---|---|---|
| `knowledge` | `knowledge_memory` | Add/rewrite a reusable entry |
| `experience` | `experience_memory` | Add a success/failure lesson |
| `task` | `task_memory` | Correct tracked task state |
| `context` | `context_memory` | Re-link session context |
| `user` | `user_memory` | Add a preference/habit |
| `research` | `research_papers/notes` | Add a reference |

**Depth note — the two-engine bug this exposed.** EchoMind ships two reflection engines: a compiled native engine and a Python fallback. The fallback normalizes the attribution fields internally, but the **native engine returns the `ReflectionOutput` object directly, bypassing the fallback's normalization entirely**. A malformed `primary_owner: "bogus"` therefore sailed through on the native path and would have been persisted verbatim. The fix moves normalization to `ReflectiveAgent._normalize_attribution` — the single point both engines pass through:

```
normalize(x) = x.lower().strip()   if x ∈ VALID_SET
             = ""                  otherwise        # unknown → not attributed
```

This is a good example of why absorption is not copy-paste: the same semantic requirement had to be enforced at a different layer in EchoMind's architecture than in Recuris's.

### 4.3 The Fingerprint Gate: Unobserved ≠ Signal

**The problem it solves.** EchoMind's RL optimizer adjusts retrieval weights from user feedback and periodically checks whether learning is actually working. The check compares a recent hit rate against a baseline:

```
success  = (1/n) Σ hits_i
baseline = (1/m) Σ baseline_j
se       = sqrt( success(1 − success) / n )
improved = success > baseline + 2·se          # ~95% one-sided
```

The blind spot: `verify_improvement` counted every feedback in the window as evidence, **including feedback on entries that were never retrieved**. An entry with `access_count = 0` has no observation — its "effectiveness" is undefined, and any difference measured on it is noise. Acting on that noise is worse than acting on nothing: a quiet period could trigger the conservative ladder ("not significant → halve the learning rate") for no reason.

**What was built.** Recuris's fingerprint principle — *read the mechanism before you read the score*; their scorecard refuses to print a score before the mechanism counters — is now enforced at the gate:

```
observed = #{ entries with access_count > 0 in the user's knowledge }
if observed == 0:
    return insufficient        # no signal — do NOT run the conservative ladder
```

Two concrete changes:

- `verify_improvement(hits, baseline, observed_count=...)` — a window with **zero observed entries** reports `insufficient` (not `not_significant`), so the conservative ladder never fires on noise. When `observed_count` is omitted entirely, behavior is exactly as before (backward compatible).
- `record_feedback` now records `task_type` on `save_hit` (previously always `''`), so hit statistics are no longer per-user only — you can see *which kind of task* is learning.

**Depth note — why `access_count`.** `hit_history` is event-level: one row per feedback event. To know whether an *entry* was ever observed, we need an entry-level counter, and `knowledge_memory.access_count` is exactly that — it increments on every retrieval that returns the entry. Using it keeps the gate dependency-free (no new table) and reproducible from stored data.

### 4.4 The Paired Bootstrap Gate (Grayscale)

**The problem it solves.** A memory system evolves by rewriting knowledge. Done carelessly, a rewrite can silently degrade the knowledge base on the strength of a single lucky or unlucky reading. Recuris's answer is admission by arithmetic: *a model proposes; arithmetic disposes.*

**What was built.** `core/learning/paired_gate.py` implements the same semantics, wired into the reflection merge behind `reflection.gate_enabled` — **grayscale default OFF**. Given paired per-item scores on the same held-out items:

```
diffs_i = cand_i − base_i                       (one value per item)
net     = mean(diffs)
floor   = max(material, 1e-9)
n_up    = #{ diffs_i >  floor }
n_dn    = #{ diffs_i < −floor }

# bootstrap resamples ITEMS, not samples
boots   = sorted{ mean( diffs[randrange(n)] for _ in range(n) ) } for 3000 draws
lo, hi  = boots[α/2·B], boots[(1−α/2)·B − 1]

accept  = (lo > 0) and (n_dn ≤ reg_cap)
```

Two details are load-bearing, and both are easy to get wrong:

1. **Bootstrap over items, not over samples.** Trials within one item are correlated; resampling them produces an interval far narrower than the evidence supports — i.e., it manufactures significance. We resample whole items (clusters), exactly as Recuris's `held_out_paired_gate` does.
2. **"Not significant" abstains — it does not reject.** Recuris's Case 1 documents two patches rejected by an underpowered gate that later measured **+11.92** on held-out tasks. A gate that treats "can't tell" as "no" destroys real improvements. The `material` floor additionally stops 0.97-vs-0.95 noise from registering as a regression, which would otherwise let the regression cap reject on pure jitter.

**Depth note — why grayscale.** Admission gates change behavior, and a change that can reject updates should not ship on by default. The gate ships OFF; enabling it is a deliberate operator choice, and its semantics are conservative in exactly one direction — it can refuse a good update, but it cannot admit a significantly harmful one.

---

## 5. What These Absorptions Give Users

The value is not abstract. Each absorption maps to something you can observe or act on:

| Absorption | What you get | Why it matters to you |
|---|---|---|
| Structured trace | **Reproducible retrieval audits** — "why didn't it remember X?" is answered from a stored row, not from recollection | You can debug memory like any other system instead of treating it as a black box |
| Structured trace | **Attribution becomes possible** — the reflection layer can link a bad outcome to a specific retrieval event (the 64.8% vs 13.0% gap) | Failures become actionable instead of merely reported |
| Structured trace | **Exact re-derivation** — every `importance` is reproducible from the record + current weights | You can prove why a memory ranked where it did |
| Component attribution | **Targeted repair, not shotgun edits** — an `invocation_miss` (ρ) is fixed by changing retrieval timing (worth +23.9), not by writing more knowledge (+2.0) | Less churn in your knowledge base; fewer low-value entries |
| Component attribution | **Honest uncertainty** — the system says "cannot attribute" rather than inventing a cause; abstention is first-class | Fewer confident-but-wrong diagnoses; you trust the attributions you do get |
| Component attribution | **Queryable history** — owner/failure_type ride the reflection `meta` JSON | "How many `invocation_miss` reflections this month?" is a query, not archaeology |
| Fingerprint gate | **No false penalties from noise** — a quiet period no longer triggers "not significant → halve LR" on pure noise | Your retrieval weights stop drifting on nothing |
| Fingerprint gate | **Trustworthy learning history** — `task_type` is recorded on hits | You can see *which kind of task* is learning well |
| Paired gate | **Memory only changes on paired evidence** — `lo > 0` and `n_dn ≤ reg_cap` before admission; weak evidence abstains and keeps current knowledge | Your knowledge base can't silently degrade on a coin-flip reading |
| Paired gate | **Bounded downside** — every applied rewrite is provably not a significant regression | Safe to enable; and it ships OFF, so nothing changes until you opt in |

**Operational cost.** None of this costs anything when unused. The trace rides data retrieval already computes; the gate is OFF by default; the attribution fields default to `""` and are ignored by any caller that doesn't read them. The upgrade adds a column and two optional fields, not a new subsystem.

---

## 6. Verification

Each absorption was verified in isolation and as a chain, against a temporary database (production untouched):

| # | Check | Result |
|---|---|---|
| 1 | Migration v12 idempotent; integrity | `user_version = 12`, `integrity ok`; legacy rows compatible |
| 2 | Trace persist/update | store writes `{}`; retrieval writes full `trace-v1` with per-entry id/source/importance |
| 3 | Attribution normalization | valid values pass; old outputs default to `""`; `"bogus"` → `""` **on both engines** |
| 4 | Fingerprint gate | `observed_count = 0` → `insufficient`; normal samples unchanged (regression-safe) |
| 5 | Paired gate math | significant improvement accepted (CI excludes zero); no-change rejected; multi-regression rejected by cap; `material` floor absorbs 0.97-vs-0.95; gate OFF = legacy behavior |
| 6 | Full-chain smoke | store → retrieve (trace) → query → reflect (attribution) → feedback (fingerprint) → shutdown → reload |

A note on how the two-engine bug was found: check #3 was originally written for the fallback path and passed; running the same check on the native engine (the one actually loaded in the development environment) revealed the bypass. The lesson is that "the tests pass" is not the same as "the requirement holds on every code path."

---

## 7. Conclusion

Recuris proves that recursive self-improvement can live in the **memory layer** of a frozen agent — and that the reflection engine's job is not to summarize failures but to **localize** them to a component that can be repaired. The evidence is quantitative: 13.0% versus 64.8% localization, and a twenty-fold difference in which component matters most (+2.0 versus +23.9).

EchoMind v1.2.19 takes the four pieces of that machinery that fit a memory engine:

1. the **trace** that makes localization possible,
2. the **attribution** that makes repair targeted,
3. the **fingerprint** that keeps noise out of learning, and
4. the **gate** that bounds evolution by paired evidence.

Together they turn reflection from a summary generator into a repair engine — and they cost nothing when unused. The remaining gap — a verified intent ledger with evidence-backed state commits — is the next structural step, and it depends on the trace infrastructure this release puts in place.

---

> **This Series:**
> Part 1: [Echomind: Why Every AI Agent Needs a Memory System](echomind-agent-memory-article-en.md)
> Part 2: [Echomind: RL Self-Learning Memory System](echomind-rl-article-en.md)
> Part 3 (A): [Echomind: Self-Reflective Agent — Reflection Engine and Memory Lifecycle](echomind-reflective-agent-part1-article-en.md)
> Part 3 (B): [Echomind: Self-Reflective Agent — Knowledge Evolution and Memory Governance](echomind-reflective-agent-part2-article-en.md)
> Part 4: Echomind × Recuris: Teaching Memory to Attribute, Not Just Summarize (this article)
