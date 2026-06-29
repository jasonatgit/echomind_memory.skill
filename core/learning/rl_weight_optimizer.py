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


class RLWeightOptimizer:
    _WEIGHT_SPEC = {
        "relevance": {"range": [0.30, 0.50], "default": [0.30, 0.50]},
        "recency":           {"range": [0.15, 0.25], "default": [0.15, 0.25]},
        "frequency":         {"range": [0.10, 0.20], "default": [0.10, 0.20]},
        "explicit_feedback": {"range": [0.10, 0.20], "default": [0.10, 0.20]},
        "trust_score":       {"range": [0.05, 0.15], "default": [0.05, 0.15]},
    }
    # Define weight key order constants, eliminate hardcoded magic numbers
    _WEIGHT_KEYS = ["relevance", "recency", "frequency", "explicit_feedback", "trust_score"]
    # state = [5 task features + 5 source ratios] = 10 维
    _TASK_FEATURE_COUNT = 5

    def __init__(
        self,
        initial_weights: Dict[str, float],
        learning_rate: float = 0.05,
        decay_factor: float = 0.98,
        max_buffer_size: int = 50,
        seed: Optional[int] = None,
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
        # Initial weight Softmax normalization
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
        # Epsilon-greedy exploration (O-11)
        self.epsilon_start = 0.1
        self.epsilon_end = 0.01
        self.epsilon_step = 0
        self._source_order = ["user", "knowledge", "experience", "task_progress",
                               "task_history", "research", "context"]

    def _get_lr(self) -> float:
        """Cosine decay learning rate from base_lr to lr_min over lr_max_steps."""
        if self.update_counter >= self.lr_max_steps:
            return self.lr_min
        frac = self.update_counter / self.lr_max_steps
        cosine = 0.5 * (1 + math.cos(math.pi * frac))
        return self.lr_min + cosine * (self.base_lr - self.lr_min)

    def _maybe_explore(self):
        """Epsilon-greedy weight perturbation."""
        eps = max(self.epsilon_end, self.epsilon_start - (self.epsilon_start - self.epsilon_end) * self.epsilon_step / 500)
        self.epsilon_step += 1
        if random.random() < eps:
            k = random.choice(self._WEIGHT_KEYS)
            self.weights[k] += random.uniform(-0.02, 0.02)
            logger.debug("[RL] Exploration: perturbed %s (eps=%.3f)", k, eps)

    @staticmethod
    def _build_feedback_features(fb: FeedbackRecord) -> dict:
        """Build task_features dict from feedback record when original context is lost."""
        mem_sources = [m.get("source", "") for m in fb.retrieved_memories[:8]]
        # Derive domain from retrieved memories
        domains = [
            (m.get("metadata", {}).get("domain", "") or
             m.get("metadata", {}).get("category", ""))
            for m in fb.retrieved_memories[:5]
        ]
        domain = max(set(domains), key=domains.count) if any(domains) else "general"
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
        weights = [self.ema_weights.get(k, 0.2) for k in self._WEIGHT_KEYS]
        score = np.dot(state[-len(self._WEIGHT_KEYS):], weights)
        return float(score)

    def add_feedback(self, feedback: FeedbackRecord):
        self.feedback_buffer.append(feedback)
        if len(self.feedback_buffer) >= 10:
            self._update_weights()
            self.feedback_buffer = []
        if len(self.feedback_buffer) > self.max_buffer_size:
            self.feedback_buffer.pop(0)

    def _update_weights(self):
        total_reward = 0
        n = len(self.feedback_buffer)

        # Cosine-decayed learning rate (O-10)
        current_lr = self._get_lr()
        self.update_counter += 1

        weight_keys = self._WEIGHT_KEYS
        for fb in self.feedback_buffer:
            reward = 1 if fb.user_feedback == "positive" else -1
            total_reward += reward

            state = self.extract_state(
                self._build_feedback_features(fb),
                fb.retrieved_memories,
            )

            pred_score = self.predict_score(state)
            for i, weight_key in enumerate(weight_keys):
                if weight_key not in self.weights:
                    continue
                source_idx = self._TASK_FEATURE_COUNT + i
                if source_idx < len(state):
                    delta = current_lr * (reward - pred_score) * state[source_idx]
                    self.weights[weight_key] += delta

        # Epsilon-greedy exploration (O-11)
        self._maybe_explore()

        # Softmax normalization (replaces clamp + sum norm, eliminates forced 0.01 issue)
        values = np.array([self.weights.get(k, 0.0) for k in weight_keys])
        exp_values = np.exp(values - np.max(values))
        softmax_values = exp_values / np.sum(exp_values)
        for i, k in enumerate(weight_keys):
            self.weights[k] = float(softmax_values[i])

        # EMA smoothing update
        for k in weight_keys:
            self.ema_weights[k] = (
                self.decay_factor * self.ema_weights[k]
                + (1 - self.decay_factor) * self.weights[k]
            )

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

    def get_current_weights(self) -> Dict[str, float]:
        return self.ema_weights.copy()

    def decay_all(self, factor: float = 0.95):
        """Decay all weights by a multiplicative factor.

        Used by reflection engine when 'forget_suggestions' are provided.
        """
        for k in self.weights:
            self.weights[k] = max(0.01, self.weights[k] * factor)
        # Softmax normalization
        values = np.array([self.weights.get(k, 0.0) for k in self._WEIGHT_KEYS])
        exp_values = np.exp(values - np.max(values))
        softmax_values = exp_values / np.sum(exp_values)
        for i, k in enumerate(self._WEIGHT_KEYS):
            self.weights[k] = float(softmax_values[i])
        # Sync EMA weights
        for k in self.ema_weights:
            self.ema_weights[k] = (
                self.decay_factor * self.ema_weights[k]
                + (1 - self.decay_factor) * self.weights[k]
            )
        logger.info(f"[RL] Weights decayed by factor={factor}, new weights: {self.ema_weights}")

    def get_history(self) -> List[Dict]:
        return self.history.copy()