from pydantic import BaseModel, Field
from datetime import datetime
from typing import Dict, Any, List


class UserMemory(BaseModel):
    user_id: str
    preferences: Dict[str, Any] = Field(default_factory=dict)
    habits: Dict[str, Any] = Field(default_factory=dict)
    history: List[Dict[str, Any]] = Field(default_factory=list)
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    version: int = 1