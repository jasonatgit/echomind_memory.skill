from pydantic import BaseModel, Field
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional


class ResearchPaper(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = "default"
    project: str = "default"
    profile: str = "default"
    title: str
    authors: List[str] = Field(default_factory=list)
    year: Optional[int] = None
    journal: Optional[str] = None
    abstract: str = ""
    keywords: List[str] = Field(default_factory=list)
    domain: str = "general"
    paper_type: str = "theory"
    key_points: List[str] = Field(default_factory=list)
    importance_score: float = 0.5
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # L-4 fix: carry the DB row's last_access_at into the in-RAM paper so
    # _freshness() can actually decay on access instead of always falling back
    # to created_at (which made paper freshness constant at 1.0). Stored as a
    # DB-format string to match the sqlite column; parsed via _parse_db_ts().
    last_access_at: str = ""


class ResearchNote(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = "default"
    project: str = "default"
    profile: str = "default"
    topic: str
    content: str
    linked_papers: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))