# echomind_memory.skill/core/llm_client.py
#
# Unified LLM client — supports OpenAI-compatible API endpoints.
# Replaces hardcoded localhost:9119 dependency with configurable endpoint.
# Also provides semantic scoring for memory retrieval (LLM-based, no embedding model).

import os
import threading
import re
import logging
from typing import List, Optional, Dict, Any

logger = logging.getLogger("LLMClient")


class LLMClient:
    """OpenAI-compatible LLM client for reflection and semantic search.

    Backward compatible with old llm.host/llm.port config:
      endpoint is auto-constructed as http://{host}:{port}/v1 when
      host and port are present but endpoint is not.
    """

    def __init__(self, config: dict):
        self._provider = config.get("provider", "openai_compatible")
        self._endpoint = self._resolve_endpoint(config)
        self._api_key = self._resolve_api_key(config)
        self._model = config.get("model", "local")
        self._temperature = config.get("temperature", 0.3)
        self._max_tokens = config.get("max_tokens", 1500)
        self._timeout = config.get("timeout", 60)
        self._semantic_model = config.get("semantic_model", "") or self._model
        self._semantic_temperature = config.get("semantic_temperature", 0)
        self._semantic_max_tokens = config.get("semantic_max_tokens", 4)

        self._available = self._provider != "none"
        if self._available:
            logger.info("LLM client: %s @ %s (model=%s)",
                        self._provider, self._endpoint, self._model)
        else:
            logger.info("LLM client: disabled (provider=none)")

    # ── internal helpers ──────────────────────────────────────────

    @staticmethod
    def _resolve_endpoint(config: dict) -> str:
        endpoint = config.get("endpoint", "")
        if endpoint:
            return endpoint.rstrip("/")
        host = config.get("host", "localhost")
        port = config.get("port", 9119)
        return f"http://{host}:{port}/v1"

    @staticmethod
    def _resolve_api_key(config: dict) -> str:
        key = config.get("api_key", "")
        if key.startswith("${") and key.endswith("}"):
            env_var = key[2:-1]
            return os.environ.get(env_var, "")
        return key

    @staticmethod
    def _parse_score(text: str) -> float:
        """Extract a 0-10 score from LLM response. Returns 0.0 on parse failure."""
        # Try to find an integer 0-10
        m = re.search(r'\b(10|[0-9])\b', text)
        if m:
            return float(m.group(1)) / 10.0
        return 0.0

    @property
    def available(self) -> bool:
        return self._available

    # ── public API ─────────────────────────────────────────────────

    def chat(self, prompt: str, **overrides) -> str:
        """Send a chat completion request. Returns response text or empty string.

        Overrides: model, temperature, max_tokens, timeout.
        """
        if not self._available:
            return ""
        try:
            import requests
            headers = {"Content-Type": "application/json"}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"

            body = {
                "model": overrides.get("model", self._model),
                "messages": [{"role": "user", "content": prompt}],
                "temperature": overrides.get("temperature", self._temperature),
                "max_tokens": overrides.get("max_tokens", self._max_tokens),
            }
            resp = requests.post(
                f"{self._endpoint}/chat/completions",
                json=body,
                headers=headers,
                timeout=overrides.get("timeout", self._timeout),
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning("LLM chat failed: %s", e)
            return ""

    def score(self, query: str, memory_text: str) -> float:
        """Semantic relevance score 0.0–1.0 between query and a memory item.

        Uses the LLM itself for semantic understanding — no embedding model needed.
        Falls back to 0.0 when LLM is unavailable.
        """
        if not self._available:
            return 0.0
        prompt = (
            "Rate how relevant this memory is to the query on a scale of 0-10.\n"
            "Reply with a single integer (0-10) and nothing else.\n\n"
            f"Query: {query}\nMemory: {memory_text[:500]}"
        )
        try:
            raw = self.chat(
                prompt,
                model=self._semantic_model,
                temperature=self._semantic_temperature,
                max_tokens=self._semantic_max_tokens,
            )
            return self._parse_score(raw)
        except Exception as e:
            logger.debug("Semantic score failed: %s", e)
            return 0.0

    def batch_score(self, query: str, items: List[Dict[str, Any]],
                    text_key: str = "content") -> List[float]:
        """Score multiple memory items against a query.

        Tries to score items in a single LLM call for efficiency.
        Falls back to individual calls if batch format fails.
        Returns list of floats (0.0–1.0) in the same order as items.
        """
        if not self._available or not items:
            return [0.0] * len(items)

        # Build a batch prompt: number each item, ask for space-separated scores
        items_text = "\n\n".join(
            f"[{i}] {item.get(text_key, str(item))[:200]}"
            for i, item in enumerate(items)
        )
        prompt = (
            f"Rate the relevance of each item to this query on a scale of 0-10.\n"
            f"Reply with {len(items)} space-separated integers (e.g. '7 3 9 1').\n"
            f"Nothing else.\n\n"
            f"Query: {query}\n\n{items_text}"
        )
        try:
            raw = self.chat(
                prompt,
                model=self._semantic_model,
                temperature=self._semantic_temperature,
                max_tokens=len(items) * 3 + 5,
            )
            scores = []
            for token in raw.strip().split():
                try:
                    s = int(token)
                    scores.append(min(max(s, 0), 10) / 10.0)
                except ValueError:
                    scores.append(0.0)
            # Pad or truncate to match items length
            while len(scores) < len(items):
                scores.append(0.0)
            return scores[:len(items)]
        except Exception as e:
            logger.debug("Batch semantic score failed, falling back: %s", e)
            return [self.score(query, item.get(text_key, str(item))) for item in items]


# ── module-level singleton ──────────────────────────────────────

_client_singleton: Optional[LLMClient] = None


_llm_client_lock = threading.Lock()

def get_llm_client(config: Optional[dict] = None) -> Optional[LLMClient]:
    """Module-level singleton factory.

    Pass config explicitly, or omit to auto-load from ConfigManager.
    Returns None when LLM is disabled (provider=none).
    """
    global _client_singleton
    with _llm_client_lock:
        if _client_singleton is None:
            if config is None:
                from .config_manager import get_config_manager
                config = get_config_manager().get_section("llm")
            client = LLMClient(config)
            _client_singleton = client
            return client if client.available else None
    return _client_singleton if _client_singleton.available else None