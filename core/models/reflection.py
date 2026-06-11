from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import List, Optional


class ReflectionOutput(BaseModel):
    """Reflection output — deserialized from LLM JSON response"""

    key_insights: List[str] = Field(
        default_factory=list, max_length=8,
        description="Key insights distilled from episodic records",
    )
    user_preferences: List[str] = Field(
        default_factory=list,
        description="User coding style / tool preferences, format: key=value",
    )
    procedural_rules: List[str] = Field(
        default_factory=list,
        description="Executable procedural rules — if-then refactor patterns",
    )
    new_knowledge: List[str] = Field(
        default_factory=list,
        description="Abstract domain or project-specific knowledge",
    )
    importance_scores: dict = Field(
        default_factory=dict,
        description="Importance scores 0-1 for each memory category",
    )
    forget_suggestions: List[str] = Field(
        default_factory=list,
        description="Old memories suggested for weight decay",
    )
    confidence: float = Field(..., ge=0, le=1)


class ReflectionRecord(BaseModel):
    """Persisted reflection record"""

    id: str
    user_id: str
    platform: str
    source_episodic_ids: List[str]
    reflection: ReflectionOutput
    meta: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))