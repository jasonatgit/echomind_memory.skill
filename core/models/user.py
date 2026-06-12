from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Dict, Any, List


class UserMemory(BaseModel):
    user_id: str
    profile: str = "default"
    preferences: Dict[str, Any] = Field(default_factory=dict)
    habits: Dict[str, Any] = Field(default_factory=dict)
    history: List[Dict[str, Any]] = Field(default_factory=list)
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    version: int = 1