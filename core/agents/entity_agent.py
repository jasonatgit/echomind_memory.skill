"""Entity extraction agent (v1.2.18 refactor, P2).

Extracted from MainMemoryAgent. Deterministic keyword fallback + optional LLM
extraction. MainMemoryAgent._extract_entities delegates here.
"""

import json
import logging
from typing import Callable, Dict, List

logger = logging.getLogger("MemoryAgent")


class EntityAgent:
    """Extract named entities (technologies/concepts/people/projects)."""

    def __init__(self, cfg, llm_getter: Callable):
        self.cfg = cfg
        self._get_llm_client = llm_getter

    def extract(self, content: str) -> List[Dict]:
        """Extract entities using LLM if available, keyword fallback otherwise."""
        llm = self._get_llm_client() if callable(self._get_llm_client) else None
        if llm:
            try:
                return self._llm_extract(llm, content)
            except Exception:
                pass
        return self._keyword_extract(content)

    def _llm_extract(self, llm, content: str) -> List[Dict]:
        prompt = "Extract named entities (technologies, concepts, people, projects) from this text. Return JSON: [{\"type\":\"technology\",\"name\":\"...\"}]"
        result = llm.chat(f"{prompt}\n\n{content[:600]}", temperature=0, max_tokens=200)
        try:
            parsed = json.loads(result)
            if isinstance(parsed, list):
                for e in parsed:
                    e.setdefault("source", "llm")
                    e.setdefault("confidence", 0.85)
                return parsed
        except Exception:
            pass
        return self._keyword_extract(content)

    def _keyword_extract(self, content: str) -> List[Dict]:
        entities = []
        kw_cfg = self.cfg.get("entities", "technologies", default=[])
        if isinstance(kw_cfg, str):
            kw_cfg = [kw_cfg]
        for kw in kw_cfg:
            if isinstance(kw, str) and kw.lower() in content.lower():
                entities.append({"type": "technology", "name": kw, "confidence": 0.6, "source": "keyword"})
        return entities[:10]
