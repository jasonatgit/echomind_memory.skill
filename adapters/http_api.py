# echomind_memory — FastAPI Service entry point (v2, SQLite)
# Based on upstream update: github.com/jasonatgit/echomind_memory.skill

import json
import os
import sys
from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
import logging
import uvicorn

from core.memory_agent import MainMemoryAgent
from core._reflective_version import get_echomind_version
from core.config_manager import get_config_manager

# ── Init ──
memory_agent = MainMemoryAgent()

cfg = get_config_manager().get_section("server")

# ── API Key Auth ──
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


def verify_api_key(api_key: str = Depends(api_key_header)):
    expected = cfg.get("api_key", "")
    if not expected:
        return None  # no key configured — allow all (backward compat)
    if api_key and api_key == expected:
        return api_key
    raise HTTPException(status_code=403, detail="Invalid or missing API key")


@asynccontextmanager
async def lifespan(app: FastAPI):
    memory_agent.enable_persistence()
    yield
    memory_agent.disable_persistence()


app = FastAPI(title="EchoMind Memory", version=get_echomind_version(), lifespan=lifespan)
cors_origins = cfg.get("cors_origins", ["http://localhost:8005"])
app.add_middleware(CORSMiddleware, allow_origins=cors_origins, allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-API-Key"])


# ── Health ──
@app.get("/health")
async def health():
    return {"status": "ok", "storage": "sqlite",
            "db": os.path.basename(str(memory_agent.db.db_path)),
            "version": get_echomind_version()}


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
    linked_papers: List[str] = []
    tags: List[str] = []


class ReflectRequest(BaseModel):
    """Reflection endpoint — build prompt or process result"""
    user_id: str
    platform: Optional[str] = "http"
    count: int = 8
    record_ids: Optional[List[str]] = None
    llm_response: Optional[str] = None


# ── Error handler (v1.2.0: avoid leaking internal details) ──
logger = logging.getLogger("EchoMind.API")

EXCEPTION_RESPONSE = {"status": "error", "detail": "Internal server error"}


async def _safe_exception(e: Exception, context: str = "") -> dict:
    logger.error(f"{context}: {e}", exc_info=True)
    return EXCEPTION_RESPONSE


# ── Routes ──
@app.post("/api/memory/retrieve")
async def api_retrieve(req: RetrieveRequest, auth=Depends(verify_api_key)):
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
            "confidence_score": float(confidence),
            "used_weights": memory_agent.rl_optimizer.get_current_weights(),
            "feedback_requested": result.get("feedback_request", False),
            "raw_memory_sources": result.get("raw_memory_sources", {}),
            "task_features": result.get("task_features", {}),
        }
    except Exception as e:
        return {
            "working_memory": [], "confidence_score": 0.0,
            "used_weights": {}, "feedback_requested": False, "error": str(e),
        }

@app.post("/api/memory/store")
async def api_store(req: StoreRequest, auth=Depends(verify_api_key)):
    try:
        memory_agent.store(
            req.user_id, req.task_id,
            [{"role": m.role, "content": m.content} for m in req.context],
            req.task_status, req.success, req.experience_summary,
            platform=req.platform, title=req.title,
        )
        return {"status": "stored", "user_id": req.user_id, "task_id": req.task_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/memory/search-sessions")
async def search_sessions(q: str = "", user_id: str = None, project: str = None, limit: int = 5):
    if not memory_agent or not memory_agent.is_persistence_enabled():
        return {"results": [], "message": "Persistence is not enabled"}
    try:
        results = memory_agent.db.search_transcripts(q, user_id, project, limit)
        return {"results": results, "count": len(results)}
    except Exception as e:
        return {"results": [], "error": str(e)}

@app.post("/api/memory/feedback")
async def api_feedback(req: FeedbackRequest, auth=Depends(verify_api_key)):
    try:
        memory_agent.record_feedback(req.user_id, req.task_id, req.feedback, req.retrieved_memories)
        return {"status": "feedback_received", "user_id": req.user_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/memory/sync-code")
async def api_sync_code(req: SyncCodeRequest, auth=Depends(verify_api_key)):
    try:
        memory_agent.sync_to_code_project(req.project_root, req.user_id)
        return {"status": "synced", "path": f"{req.project_root}/.echomind"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/research/paper")
async def api_add_paper(req: ResearchPaperRequest, auth=Depends(verify_api_key)):
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
async def api_add_note(req: ResearchNoteRequest, auth=Depends(verify_api_key)):
    try:
        note_id = memory_agent.add_research_note(
            user_id=req.user_id, topic=req.topic, content=req.content,
            linked_papers=req.linked_papers, tags=req.tags)
        return {"status": "stored", "note_id": note_id, "topic": req.topic}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Reflection (v1.1.0) ──
@app.post("/api/reflect")
async def api_reflect(req: ReflectRequest, auth=Depends(verify_api_key)):
    """
    Two-phase reflection endpoint:
    - llm_response=None → returns prompt for caller to process (Path B)
    - llm_response=... → parses and writes back (Path A / process)
    """
    if req.llm_response is None:
        records = memory_agent.get_recent_episodic(req.user_id, req.count)
        prompt, record_ids = memory_agent.reflective.build_prompt(
            records, req.user_id, req.platform or "http"
        )
        return {
            "phase": "build",
            "prompt": prompt,
            "record_ids": record_ids,
            "record_count": len(records),
        }
    else:
        # Fetch full records (not just IDs) for process_result
        full_records = memory_agent.get_recent_episodic(req.user_id, req.count)
        # Filter to requested IDs
        id_set = set(req.record_ids or [])
        records = [r for r in full_records if r.get("id") in id_set]
        if not records:
            records = [{"id": rid, "content": "", "text": ""} for rid in (req.record_ids or [])]
        output = memory_agent.reflective.process_result(
            raw_response=req.llm_response,
            records=records,
            user_id=req.user_id,
            platform=req.platform or "http",
        )
        if output is None:
            raise HTTPException(
                status_code=400,
                detail="Reflection failed: parse error or confidence too low",
            )
        return {
            "phase": "done",
            "insights": len(output.key_insights),
            "preferences": len(output.user_preferences),
            "rules": len(output.procedural_rules),
            "knowledge": len(output.new_knowledge),
            "confidence": output.confidence,
        }


# ── Config (v1.1.0) ──
class ConfigUpdateRequest(BaseModel):
    section: str
    key: str
    value: Any


@app.get("/api/config")
async def api_get_config(auth=Depends(verify_api_key)):
    cfg = get_config_manager()
    return {
        "config_path": cfg.config_path,
        "sections": {
            "rl": cfg.get_section("rl"),
            "reflection": cfg.get_section("reflection"),
            "retrieval": cfg.get_section("retrieval"),
            "inference": cfg.get_section("inference"),
            "llm": {k: v for k, v in cfg.get_section("llm").items() if k != "api_key"},
            "server": cfg.get_section("server"),
        }
    }


@app.post("/api/config/parameter")
async def api_set_config_param(req: ConfigUpdateRequest, auth=Depends(verify_api_key)):
    cfg = get_config_manager()
    key_path = f"{req.section}.{req.key}"
    cfg.set_runtime(key_path, req.value)
    return {"status": "ok", "key": key_path, "value": req.value}


@app.post("/api/config/reload")
async def api_reload_config(auth=Depends(verify_api_key)):
    cfg = get_config_manager()
    cfg.reload()
    return {"status": "reloaded", "config_path": cfg.config_path}


# ── Entry ──
if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else cfg.get("port", 8005)
    host = cfg.get("host", "127.0.0.1")
    print(f"EchoMind Memory v{get_echomind_version()} — HTTP API Mode")
    print(f"  Endpoint: http://{host}:{port}")
    print(f"  Docs:     http://{host}:{port}/docs")
    uvicorn.run(app, host=host, port=port, log_level="info")