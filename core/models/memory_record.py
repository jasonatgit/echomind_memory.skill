"""MemoryRecord — a scored retrieval candidate.

Extracted from core/memory_agent.py (v1.2.18 refactor) so pure scoring
helpers (core/scoring.py) can reference the type without importing the
MainMemoryAgent module (avoids a circular import).
"""

from typing import Any, Dict

from pydantic import BaseModel


class MemoryRecord(BaseModel):
    source: str
    content: str
    importance: float
    metadata: Dict[str, Any]
    relevance: float = 0.5      # 检索时的相关性得分，供 RL 优化器使用
    trust_score: float = 0.5    # 记忆的可信度得分，供 RL 优化器使用
