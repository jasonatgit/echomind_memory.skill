from pydantic import BaseModel, Field
import uuid
from datetime import datetime
from typing import List


class ExperienceEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    task_type: str
    success: bool
    steps_sequence: List[str] = Field(default_factory=list)
    summary: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    frequency: int = 1