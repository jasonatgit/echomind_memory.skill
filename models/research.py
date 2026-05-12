from pydantic import BaseModel, Field
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional


class ResearchPaper(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
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
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ResearchNote(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = "default"
    topic: str
    content: str
    linked_papers: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)