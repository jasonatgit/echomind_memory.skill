import json
import logging
from datetime import datetime
from typing import Dict, List, Optional
import numpy as np
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class FeedbackRecord(BaseModel):
    user_id: str
    task_id: str
    retrieved_memories: List[Dict]
    user_feedback: str  # "positive" or "negative"
    timestamp: datetime = datetime.utcnow()


class RLWeightOptimizer:
    def __init__(
        self,
        initial_weights: Dict[str, float],
        learning_rate: float = 0.05,
        decay_factor: float = 0.98,
    ):
        self.weights = initial_weights.copy()
        self.ema_weights = initial_weights.copy()
        self.feedback_buffer: List[FeedbackRecord] = []
        self.learning_rate = learning_rate
        self.decay_factor = decay_factor
        self.update_counter = 0
        self.max_buffer_size = 50
        self.history: List[Dict] = []

    def extract_state(self, task_features: Dict, retrieved_memories: List[Dict]) -> np.ndarray:
        task_type_map = {
            "analysis": 1, "general": 0,
            "finance": 1, "medical": 1, "legal": 1,
        }
        domain_map = {"finance": 1, "medical": 1, "legal": 1, "general": 0}

        source_count = {
            "user": 0, "knowledge": 0, "experience": 0,
            "task_progress": 0, "task_history": 0,
        }
        for mem in retrieved_memories[:8]:
            source = mem.get("source", "unknown")
            if source in source_count:
                source_count[source] += 1

        total = sum(source_count.values())
        source_ratio = [
            source_count[k] / total if total > 0 else 0.0 for k in source_count.keys()
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
        sources = ["user", "knowledge", "experience", "task_progress", "task_history"]
        weights = [self.ema_weights.get(s, 0.2) for s in sources]
        score = np.dot(state[-5:], weights)
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

        for fb in self.feedback_buffer:
            reward = 1 if fb.user_feedback == "positive" else -1
            total_reward += reward

            state = self.extract_state(
                fb.retrieved_memories[0].get("metadata", {}) if fb.retrieved_memories else {},
                fb.retrieved_memories,
            )

            pred_score = self.predict_score(state)
            for i, weight_key in enumerate(
                ["relevance", "recency", "frequency", "explicit_feedback", "trust_score"]
            ):
                if weight_key not in self.weights:
                    continue
                if i < len(state):
                    delta = self.learning_rate * (reward - pred_score) * state[i]
                    self.weights[weight_key] += delta

        total = sum(self.weights.values())
        for k in self.weights:
            self.weights[k] = max(0.01, self.weights[k] / total)

        for k in self.weights:
            self.ema_weights[k] = (
                self.decay_factor * self.ema_weights[k]
                + (1 - self.decay_factor) * self.weights[k]
            )

        self.history.append({
            "timestamp": datetime.utcnow().isoformat(),
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

    def get_history(self) -> List[Dict]:
        return self.history.copy()