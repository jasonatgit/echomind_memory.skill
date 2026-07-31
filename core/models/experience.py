from pydantic import BaseModel, Field
import uuid
from datetime import datetime, timezone
from typing import List, Optional


class ExperienceEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    task_id: str = ""
    project: str = "default"
    profile: str = "default"
    session_id: str = ""
    session_title: str = ""
    task_type: str
    success: bool
    steps_sequence: List[str] = Field(default_factory=list)
    summary: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_access_at: Optional[datetime] = None
    tags: List[str] = Field(default_factory=list)
    frequency: int = 1