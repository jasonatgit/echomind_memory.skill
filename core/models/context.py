from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import List


class ContextMessage(BaseModel):
    role: str
    content: Optional[str] = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ContextMemory(BaseModel):
    messages: List[ContextMessage] = Field(default_factory=list)
    max_tokens: int = 4096
    window_size: int = 10