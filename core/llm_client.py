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
        host = config.get("host") or "localhost"
        port = config.get("port") or 9119
        return f"http://{host}:{port}/v1"

    @staticmethod
    def _resolve_api_key(config: dict) -> str:
        import re as _re
        key = config.get("api_key", "")
        _ENV_VAR_PATTERN = _re.compile(r'^\$\{[A-Za-z_][A-Za-z0-9_]*\}$')
        if _ENV_VAR_PATTERN.match(key):
            env_var = key[2:-1]
            return os.environ.get(env_var, "")
        return key

    @staticmethod
    def _parse_score(text: str) -> float:
        """Extract a 0-10 score from LLM response. Returns 0.0 on parse failure.
        Matches integer or float values; no word boundary (supports CJK text)."""
        m = re.search(r'(10|\d+(?:\.\d+)?)', text)
        if m:
            return min(max(float(m.group(1)), 0.0), 10.0) / 10.0
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
            try:
                content = data["choices"][0]["message"]["content"]
                if content is None or content.strip() == "":
                    reason = data.get("choices", [{}])[0].get("finish_reason", "?")
                    logger.warning("LLM returned empty content (finish_reason=%s)", reason)
                    return ""
                return content
            except (KeyError, IndexError, TypeError):
                logger.warning("LLM returned unexpected response format: %s", str(data)[:200])
                return ""
        except Exception as e:
            logger.warning("LLM chat failed: %s", e)
            return ""

    def score(self, query: str, memory_text: str, lang: str = "en") -> float:
        """Semantic relevance score 0.0–1.0 between query and a memory item.

        Uses the LLM itself for semantic understanding — no embedding model needed.
        Falls back to 0.0 when LLM is unavailable.
        """
        if not self._available:
            return 0.0
        from .lang_utils import get_prompt
        prompt = get_prompt("score", lang, query=query, memory_text=memory_text[:500])
        if not prompt:
            return 0.0
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
                    text_key: str = "content", lang: str = "en") -> List[float]:
        """Score multiple memory items against a query.

        Scores items in batches of 5 to avoid LLM output misalignment.
        Falls back to individual calls if batch format fails.
        Returns list of floats (0.0–1.0) in the same order as items.
        """
        if not self._available or not items:
            return [0.0] * len(items)

        batch_size = 5
        all_scores = []
        for start in range(0, len(items), batch_size):
            batch = items[start:start + batch_size]
            all_scores.extend(self._batch_score_inner(query, batch, text_key, lang))
        return all_scores

    def _batch_score_inner(self, query: str, items: List[Dict[str, Any]],
                           text_key: str = "content", lang: str = "en") -> List[float]:
        """Score a single batch of items (max 5)."""
        def _get_text(item, idx):
            if isinstance(item, dict):
                return str(item.get(text_key, ""))[:200]
            return str(item)[:200]
        items_text = "\n\n".join(
            f"[{i}] {_get_text(item, i)}"
            for i, item in enumerate(items)
        )
        from .lang_utils import get_prompt
        prompt = get_prompt("batch_score", lang, n=len(items),
                            query=query, items_text=items_text)
        if not prompt:
            return [0.0] * len(items)
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
            return [self.score(query, _get_text(item, i), lang) for i, item in enumerate(items)]


# ── module-level singleton ──────────────────────────────────────

_client_singleton: Optional[LLMClient] = None


_llm_client_lock = threading.Lock()

def get_llm_client(config: Optional[dict] = None) -> Optional[LLMClient]:
    """Module-level singleton factory.

    Pass config explicitly, or omit to auto-load from ConfigManager.
    Returns None when LLM is disabled (provider=none).
    Use force_reload=True to reinitialize after config reload.
    """
    global _client_singleton
    with _llm_client_lock:
        if config is not None:
            client = LLMClient(config)
            _client_singleton = client
            return client if client.available else None
        if _client_singleton is None:
            if config is None:
                from .config_manager import get_config_manager
                config = get_config_manager().get_section("llm")
            client = LLMClient(config)
            _client_singleton = client
            return client if client.available else None
        result = _client_singleton
        return result if result and result.available else None


def reload_llm_client():
    """Force reinitialize LLM client singleton (call after config reload)."""
    global _client_singleton
    with _llm_client_lock:
        if _client_singleton is not None:
            _client_singleton = None