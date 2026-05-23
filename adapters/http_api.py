# echomind_memory — FastAPI 服务入口 (v2, SQLite)
# 基于上游更新：github.com/jasonatgit/echomind_memory.skill

import json
import os
import sys
from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from core.memory_agent import MainMemoryAgent

# ── Init ──
memory_agent = MainMemoryAgent()


@asynccontextmanager
async def lifespan(app: FastAPI):
    memory_agent.enable_persistence()
    yield


app = FastAPI(title="EchoMind Memory", version="2.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── Health ──
@app.get("/health")
async def health():
    return {"status": "ok", "storage": "sqlite", "db": str(memory_agent.db.db_path)}


# ── Models ──
class RetrieveRequest(BaseModel):
    user_id: str
    platform: Optional[str] = None
    query: str
    task_id: Optional[str] = None
    max_results: int = 5

class ContextMessage(BaseModel):
    role: str
    content: str

class StoreRequest(BaseModel):
    user_id: str
    platform: Optional[str] = None
    task_id: str
    title: Optional[str] = None
    context: List[ContextMessage]
    task_status: str
    success: bool = False
    experience_summary: Optional[str] = None

class FeedbackRequest(BaseModel):
    user_id: str
    task_id: str
    feedback: str
    retrieved_memories: List[Dict[str, Any]]

class SyncCodeRequest(BaseModel):
    project_root: str
    user_id: str

class ResearchPaperRequest(BaseModel):
    title: str
    authors: Optional[List[str]] = None
    year: Optional[int] = None
    journal: Optional[str] = None
    abstract: str = ""
    keywords: Optional[List[str]] = None
    domain: str = "general"
    paper_type: str = "theory"
    key_points: Optional[List[str]] = None
    importance_score: float = 0.5

class ResearchNoteRequest(BaseModel):
    user_id: str
    topic: str
    content: str
    linked_papers: Optional[List[str]] = None
    tags: Optional[List[str]] = None


# ── Routes ──
@app.post("/api/memory/retrieve")
async def api_retrieve(req: RetrieveRequest):
    try:
        result = memory_agent.retrieve_for_task(req.query, req.user_id, req.task_id, platform=req.platform)
        working = [
            {"source": m.source, "content": m.content,
             "importance": m.importance, "metadata": m.metadata}
            for m in result["working_memory"][:req.max_results]
        ]
        confidence = (
            sum(m.importance for m in result["working_memory"])
            / max(len(result["working_memory"]), 1)
        )
        return {
            "working_memory": working,
            "raw_memory_sources": result.get("raw_memory_sources", {}),
            "experience_memory": result.get("raw_memory_sources", {}).get("experience", []),
            "knowledge_memory": result.get("raw_memory_sources", {}).get("knowledge", []),
            "confidence_score": float(confidence),
            "used_weights": memory_agent.rl_optimizer.get_current_weights(),
            "feedback_requested": result.get("feedback_request", False),
        }
    except Exception as e:
        return {
            "working_memory": [], "raw_memory_sources": {},
            "experience_memory": [], "knowledge_memory": [],
            "confidence_score": 0.0,
            "used_weights": {}, "feedback_requested": False, "error": str(e),
        }

@app.post("/api/memory/store")
async def api_store(req: StoreRequest):
    try:
        memory_agent.store(
            req.user_id, req.task_id,
            [{"role": m.role, "content": m.content} for m in req.context],
            req.task_status, req.success, req.experience_summary,
            platform=req.platform,
            title=req.title,
        )
        return {"status": "stored", "user_id": req.user_id, "task_id": req.task_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/memory/feedback")
async def api_feedback(req: FeedbackRequest):
    try:
        memory_agent.record_feedback(req.user_id, req.task_id, req.feedback, req.retrieved_memories)
        return {"status": "feedback_received", "user_id": req.user_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/memory/sync-code")
async def api_sync_code(req: SyncCodeRequest):
    try:
        memory_agent.sync_to_code_project(req.project_root, req.user_id)
        return {"status": "synced", "path": f"{req.project_root}/.echomind"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/research/paper")
async def api_add_paper(req: ResearchPaperRequest):
    try:
        paper_id = memory_agent.add_research_paper(
            title=req.title, authors=req.authors, year=req.year,
            journal=req.journal, abstract=req.abstract, keywords=req.keywords,
            domain=req.domain, paper_type=req.paper_type,
            key_points=req.key_points, importance_score=req.importance_score)
        return {"status": "stored", "paper_id": paper_id, "title": req.title}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/research/note")
async def api_add_note(req: ResearchNoteRequest):
    try:
        note_id = memory_agent.add_research_note(
            user_id=req.user_id, topic=req.topic, content=req.content,
            linked_papers=req.linked_papers, tags=req.tags)
        return {"status": "stored", "note_id": note_id, "topic": req.topic}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Entry ──
if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8005
    print(f"🚀 EchoMind Memory v2 (SQLite) on http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")