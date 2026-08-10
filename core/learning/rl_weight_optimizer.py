import json
import logging
import math
import random
from datetime import datetime, timezone
from typing import Dict, List, Optional
import numpy as np
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class FeedbackRecord(BaseModel):
    user_id: str
    task_id: str
    retrieved_memories: List[Dict]
    user_feedback: str  # "positive" or "negative"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = Field(default_factory=dict)


class RLWeightOptimizer:
    _WEIGHT_SPEC = {
        "relevance": {"range": [0.30, 0.50], "default": [0.30, 0.50]},
        "recency":           {"range": [0.15, 0.25], "default": [0.15, 0.25]},
        "frequency":         {"range": [0.10, 0.20], "default": [0.10, 0.20]},
        "explicit_feedback": {"range": [0.10, 0.20], "default": [0.10, 0.20]},
        "trust_score":       {"range": [0.05, 0.15], "default": [0.05, 0.15]},
    }
    _WEIGHT_KEYS = ["relevance", "recency", "frequency", "explicit_feedback", "trust_score"]
    _TASK_FEATURE_COUNT = 5
    # RCW mapping: which source types influence each weight dimension.
    _WEIGHT_SOURCE_MAP = {
        "relevance":         ["user", "knowledge", "research"],
        "recency":           ["context", "task_history"],
        "frequency":         ["experience"],
        "explicit_feedback": ["user"],
        "trust_score":       ["knowledge", "experience", "research"],
    }

    def __init__(
        self,
        initial_weights: Dict[str, float],
        learning_rate: float = 0.05,
        decay_factor: float = 0.98,
        max_buffer_size: int = 50,
        seed: Optional[int] = None,
        kpop_threshold: float = 2.0,
        kpop_max_extra: float = 0.3,
    ):
        if seed is not None:
            random.seed(seed)
        self.weights = {}
        for key, spec in self._WEIGHT_SPEC.items():
            cfg_val = initial_weights.get(key, spec["default"])
            if isinstance(cfg_val, (list, tuple)) and len(cfg_val) == 2:
                self.weights[key] = random.uniform(float(cfg_val[0]), float(cfg_val[1]))
            else:
                self.weights[key] = float(cfg_val)
        init_vals = np.array([self.weights.get(k, 0.0) for k in self._WEIGHT_KEYS])
        exp_vals = np.exp(init_vals - np.max(init_vals))
        softmax_vals = exp_vals / np.sum(exp_vals)
        for i, k in enumerate(self._WEIGHT_KEYS):
            self.weights[k] = float(softmax_vals[i])
        self.ema_weights = self.weights.copy()
        self.feedback_buffer: List[FeedbackRecord] = []
        self.learning_rate = learning_rate
        self.base_lr = learning_rate
        self.lr_min = 0.005
        self.lr_max_steps = 1000
        self.decay_factor = decay_factor
        self.update_counter = 0
        self.max_buffer_size = max_buffer_size
        self.history: List[Dict] = []
        self._cumulative_feedback_count = 0
        self.epsilon_start = 0.1
        self.epsilon_end = 0.01
        self.epsilon_step = 0
        self._source_order = ["user", "knowledge", "experience", "task_progress",
                               "task_history", "research", "context"]
        self.policy_snapshots: List[Dict] = []
        self.policy_snapshot_every = 100
        self.kpop_threshold = kpop_threshold
        self.kpop_max_extra = kpop_max_extra

    def snapshot_policy(self):
        """Record pre-update policy snapshot for KPop divergence tracking."""
        if self.policy_snapshots and self._cumulative_feedback_count - self.policy_snapshots[-1].get("total_fb", 0) < self.policy_snapshot_every:
            return
        self.policy_snapshots.append({
            "total_fb": self._cumulative_feedback_count,
            "weights": self.ema_weights.copy(),
            "softmax_dist": self._softmax(np.array([self.ema_weights[k] for k in self._WEIGHT_KEYS])).tolist(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        if len(self.policy_snapshots) > 20:
            self.policy_snapshots.pop(0)

    def _get_lr(self) -> float:
        if self.update_counter >= self.lr_max_steps:
            return self.lr_min
        frac = self.update_counter / self.lr_max_steps
        cosine = 0.5 * (1 + math.cos(math.pi * frac))
        return self.lr_min + cosine * (self.base_lr - self.lr_min)

    def _maybe_explore(self):
        eps = max(self.epsilon_end, self.epsilon_start - (self.epsilon_start - self.epsilon_end) * self.epsilon_step / 500)
        self.epsilon_step += 1
        if random.random() < eps:
            k = random.choice(self._WEIGHT_KEYS)
            self.weights[k] += random.uniform(-0.02, 0.02)
            logger.debug("[RL] Exploration: perturbed %s (eps=%.3f)", k, eps)

    def _compute_baseline(self) -> float:
        recent = self.history[-20:]
        if not recent or len(recent) < 3:
            return 0.0
        weights = np.linspace(0.5, 1.0, len(recent))
        try:
            return float(np.average([h["avg_reward"] for h in recent], weights=weights))
        except Exception:
            return 0.0

    def _compute_rcw_advantages(self, fb: FeedbackRecord) -> Dict[str, float]:
        """Reward Contribution Weighting — returns {weight_key: multiplier} (non-negative).

        For each source type, aggregate rel × trust scores, normalize to sum 1.0,
        then map to weight dimensions via _WEIGHT_SOURCE_MAP.
        Returns non-negative weights so caller can apply feedback direction
        independently without double-counting sign.
        """
        source_scores = {}
        source_counts = {}
        for mem in fb.retrieved_memories[:8]:
            source = mem.get("source", "context")
            rel = mem.get("relevance", 0.5)
            meta = mem.get("metadata", {})
            if isinstance(meta, dict) and "trust_score" in meta:
                trust = meta["trust_score"]
            elif "trust_score" in mem:
                trust = mem["trust_score"]
            else:
                trust = 0.5
            source_scores.setdefault(source, 0.0)
            source_scores[source] += rel * trust
            source_counts.setdefault(source, 0)
            source_counts[source] += 1
        if not source_scores:
            return {k: 1.0 for k in self._WEIGHT_KEYS}

        for s in source_scores:
            source_scores[s] /= max(1, source_counts[s])
        total = sum(source_scores.values()) + 1e-8
        normalized = {s: v / total for s, v in source_scores.items()}

        result = {}
        for wk in self._WEIGHT_KEYS:
            mapped = self._WEIGHT_SOURCE_MAP.get(wk, [])
            if not mapped:
                result[wk] = 1.0
                continue
            values = [normalized.get(s, 0.0) for s in mapped]
            avg = sum(values) / len(values)
            # M-4 fix: if no mapped source for this weight dimension appeared in
            # the feedback's memories, fall back to a neutral multiplier (1.0)
            # instead of 0.0. A 0.0 would make delta = lr*(advantage - pred)*0 = 0
            # and permanently freeze that dimension (e.g. explicit_feedback has
            # no "user" memory in the batch).
            result[wk] = avg if avg > 0 else 1.0
        return result

    @staticmethod
    def _build_feedback_features(fb: FeedbackRecord) -> dict:
        mem_sources = [m.get("source", "") for m in fb.retrieved_memories[:8]]
        domains = [
            (m.get("metadata", {}).get("domain", "") or
             m.get("metadata", {}).get("category", ""))
            for m in fb.retrieved_memories[:5]
        ]
        domains = [d for d in domains if d]  # filter empty strings
        domain = max(set(domains), key=domains.count) if domains else "general"
        return {
            "task_type": "general",
            "domain": domain,
            "requires_knowledge": "knowledge" in mem_sources or "research" in mem_sources,
            "is_complex": len(fb.retrieved_memories) > 5,
            "has_history": "task_history" in mem_sources or "context" in mem_sources,
        }

    def extract_state(self, task_features: Dict, retrieved_memories: List[Dict]) -> np.ndarray:
        task_type_map = {
            "analysis": 1, "general": 0,
            "finance": 1, "medical": 1, "legal": 1,
        }
        domain_map = {"finance": 1, "medical": 1, "legal": 1, "general": 0}

        source_count = {
            "user": 0, "knowledge": 0, "experience": 0,
            "task_progress": 0, "task_history": 0,
            "research": 0, "context": 0,
        }
        for mem in retrieved_memories[:8]:
            source = mem.get("source", "unknown")
            if source in source_count:
                source_count[source] += 1
        if len(retrieved_memories) > 8:
            logger.debug("extract_state: truncated %d memories to 8 for state extraction",
                        len(retrieved_memories) - 8)

        total = sum(source_count.values())
        source_ratio = [
            source_count[k] / total if total > 0 else 0.0 for k in self._source_order
        ]

        state = [
            task_type_map.get(task_features.get("task_type"), 0),
            domain_map.get(task_features.get("domain"), 0),
            task_features.get("requires_knowledge", 0),
            task_features.get("is_complex", 0),
            task_features.get("has_history", 0),
        ] + source_ratio
        return np.array(state, dtype=np.float32)

    def predict_score(self, state: np.ndarray) -> float:
        """Predict expected reward using proper source→weight mapping.

        Maps 7 source ratios to 5 weight dimensions via _WEIGHT_SOURCE_MAP,
        then dots with weights. Task features contribute as a scaled binary sum.
        """
        w = [self.ema_weights.get(k, 0.2) for k in self._WEIGHT_KEYS]
        source_ratios = state[self._TASK_FEATURE_COUNT:]
        n_ratios = len(source_ratios)

        # Build source ratio dict: {source_name: ratio}
        source_names = self._source_order
        source_dict = {}
        for i, name in enumerate(source_names):
            source_dict[name] = float(source_ratios[i]) if i < n_ratios else 0.0

        # Map source ratios to weight dimensions via _WEIGHT_SOURCE_MAP
        mapped_scores = []
        for wk in self._WEIGHT_KEYS:
            mapped_sources = self._WEIGHT_SOURCE_MAP.get(wk, [])
            if mapped_sources:
                vals = [source_dict.get(s, 0.0) for s in mapped_sources]
                mapped_scores.append(sum(vals) / len(vals))
            else:
                mapped_scores.append(0.0)

        # Dot product: 5 mapped scores × 5 weights
        source_part = float(np.dot(np.array(mapped_scores), np.array(w)))

        # Task features contribute as binary flag sum × avg weight × 0.3 scale
        task_features = state[:self._TASK_FEATURE_COUNT]
        avg_w = float(np.mean(w)) if w else 0.2
        task_part = float(np.sum(task_features)) * avg_w * 0.3 / max(len(task_features), 1)
        return task_part + source_part

    def add_feedback(self, feedback: FeedbackRecord):
        snap = feedback.metadata.get("weights_snapshot")
        if snap and isinstance(snap, dict):
            current = np.array([self.weights.get(k, 0.2) for k in self._WEIGHT_KEYS])
            snap_arr = np.array([snap.get(k, 0.2) for k in self._WEIGHT_KEYS])
            safe = np.maximum(snap_arr, 1e-6)
            ratios = current / safe
            in_bounds = (ratios >= 0.5) & (ratios <= 2.0)
            safe_ratio = float(in_bounds.mean())
            lr_mult = max(0.3, safe_ratio ** 2) if safe_ratio < 0.8 else 1.0
            feedback.metadata["lr_multiplier"] = lr_mult

        self.feedback_buffer.append(feedback)
        _update_threshold = min(10, self.max_buffer_size)
        if len(self.feedback_buffer) >= _update_threshold:
            self._update_weights()
            self.feedback_buffer = []
        if len(self.feedback_buffer) > self.max_buffer_size:
            self.feedback_buffer.pop(0)

    def _update_weights(self):
        # Snapshot pre-update weights for divergence tracking
        self.snapshot_policy()

        total_reward = 0
        n = len(self.feedback_buffer)

        current_lr = self._get_lr()
        self.update_counter += 1

        weight_keys = self._WEIGHT_KEYS
        baseline = self._compute_baseline()
        for fb in self.feedback_buffer:
            raw_reward = 1 if fb.user_feedback == "positive" else -1
            advantage = raw_reward - baseline
            lr_mult = fb.metadata.get("lr_multiplier", 1.0)
            effective_lr = current_lr * lr_mult
            total_reward += raw_reward

            state = self.extract_state(
                self._build_feedback_features(fb),
                fb.retrieved_memories,
            )

            pred_score = self.predict_score(state)
            rcw_map = self._compute_rcw_advantages(fb)
            for weight_key in weight_keys:
                if weight_key not in self.weights:
                    continue
                rcw = rcw_map.get(weight_key, 1.0)
                delta = effective_lr * (advantage - pred_score) * rcw
                self.weights[weight_key] += delta

        self._maybe_explore()

        values = np.array([self.weights.get(k, 0.0) for k in weight_keys])
        exp_values = np.exp(values - np.max(values))
        softmax_values = exp_values / np.sum(exp_values)
        for i, k in enumerate(weight_keys):
            self.weights[k] = float(softmax_values[i])

        for k in weight_keys:
            self.ema_weights[k] = (
                self.decay_factor * self.ema_weights[k]
                + (1 - self.decay_factor) * self.weights[k]
            )

        self._cumulative_feedback_count += n
        self.history.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "feedback_count": n,
            "avg_reward": total_reward / n,
            "weights": self.ema_weights.copy(),
        })
        logger.info(f"[RL] Updated weights after {n} feedbacks. Avg reward: {total_reward/n:.2f}")
        logger.info(f"[RL] Weights: {self.ema_weights}")
        if len(self.history) > 100:
            self.history.pop(0)

    def load_weights_for_user(self, weights: Dict[str, float] = None):
        """Load per-user weights into the optimizer.

        If weights is None or empty, reset to deterministic defaults built from
        the _WEIGHT_SPEC midpoints (softmax-normalized) instead of silently
        keeping the previous user's weights — otherwise a user with no saved
        weights inherits the last-loaded user's weights, leaking per-user
        isolation.  Called before retrieve_for_task.
        """
        if not weights:
            self.weights = self._default_weights()
            self.ema_weights = self.weights.copy()
            return
        self.weights = weights.copy()
        self.ema_weights = weights.copy()

    def _default_weights(self) -> Dict[str, float]:
        """Deterministic default weights from _WEIGHT_SPEC range midpoints,
        softmax-normalized (matches the invariant used by __init__/_update_weights)."""
        mids = [(spec["range"][0] + spec["range"][1]) / 2.0 for spec in self._WEIGHT_SPEC.values()]
        arr = np.array(mids, dtype=float)
        exp = np.exp(arr - np.max(arr))
        soft = exp / np.sum(exp)
        return {k: float(soft[i]) for i, k in enumerate(self._WEIGHT_KEYS)}

    def get_current_weights(self) -> Dict[str, float]:
        return self.ema_weights.copy()

    def _softmax(self, w: np.ndarray) -> np.ndarray:
        e = np.exp(w - np.max(w))
        return e / np.sum(e)

    def _compute_divergence(self) -> float:
        if not self.policy_snapshots:
            return 0.0
        current_w = np.array([self.ema_weights[k] for k in self._WEIGHT_KEYS])
        current_p = self._softmax(current_w)
        snap = self.policy_snapshots[-1]["weights"]
        target_w = np.array([snap[k] for k in self._WEIGHT_KEYS])
        target_p = self._softmax(target_w)
        eps = 1e-8
        kl_fwd = float(np.sum(current_p * np.log((current_p + eps) / (target_p + eps))))
        kl_rev = float(np.sum(target_p * np.log((target_p + eps) / (current_p + eps))))
        return max(kl_fwd, kl_rev)

    def decay_all(self, factor: float = 0.95):
        """Differential decay: pull divergent weights back toward snapshot.

        Previous implementation multiplied all weights by the same factor then
        softmax-normalized, which is a mathematical identity (no effect).
        This version applies per-dimension decay proportional to divergence,
        clamps to _WEIGHT_SPEC ranges, then linearly renormalizes to sum=1 so
        the result stays consistent with the _update_weights invariant.

        H-2 fixes:
        - dim_div now compares EMA-current vs EMA-snapshot (both EMA), instead
          of raw-current vs EMA-snapshot which systematically overstated
          divergence because raw lags EMA.
        - After clamping, weights are linearly normalized to sum to 1.0 (not
          softmax, which would cancel the differential decay) so downstream
          scoring never sees two different "weight" semantics across methods.
        """
        divergence = self._compute_divergence()
        extra = 0.0
        if divergence > self.kpop_threshold:
            extra = min(self.kpop_max_extra, (divergence - self.kpop_threshold) * 0.05)
        effective_base = max(0.5, factor - extra)

        # Per-dimension differential decay: weights farther from snapshot decay more
        snap = self.policy_snapshots[-1]["weights"] if self.policy_snapshots else {}
        for k in self._WEIGHT_KEYS:
            snap_val = snap.get(k, self.ema_weights.get(k, 0.2))
            current_ema = self.ema_weights.get(k, 0.2)
            current_raw = self.weights.get(k, 0.2)
            # Dimension-specific decay measured on the EMA distribution (matches
            # _compute_divergence); pull is applied to the raw weights.
            dim_div = abs(current_ema - snap_val)
            dim_factor = max(0.3, effective_base - dim_div * 0.5)
            # Pull toward snapshot value, not just shrink
            self.weights[k] = current_raw * dim_factor + snap_val * (1 - dim_factor)
            # Clamp to spec range
            lo, hi = self._WEIGHT_SPEC[k]["range"]
            self.weights[k] = max(lo, min(hi, self.weights[k]))

        # Restore the sum-to-1 invariant that _update_weights maintains.
        total = sum(self.weights[k] for k in self._WEIGHT_KEYS)
        if total > 0:
            for k in self._WEIGHT_KEYS:
                self.weights[k] /= total

        # EMA smooth (no softmax — it would cancel the differential decay)
        for k in self._WEIGHT_KEYS:
            self.ema_weights[k] = (
                self.decay_factor * self.ema_weights.get(k, 0.2)
                + (1 - self.decay_factor) * self.weights[k]
            )
        logger.info(f"[RL] decay_all: base_factor={effective_base:.3f} (div={divergence:.2f}, extra={extra:.3f})")

    def get_history(self) -> List[Dict]:
        return self.history.copy()
