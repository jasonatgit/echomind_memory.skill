from pydantic import BaseModel, Field
from datetime import datetime, timezone
import uuid
from typing import List, Dict, Any


class TaskMemory(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    task_id: str
    project: str = "default"
    session_id: str = ""
    session_title: str = ""
    title: str
    status: str
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = Field(default_factory=dict)