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
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import logging
import uvicorn

from core.memory_agent import MainMemoryAgent
from core._reflective_version import get_echomind_version
from core.config_manager import get_config_manager
from core.models.context import ContextMessage

logger = logging.getLogger("EchoMind.API")

# ── Init ──
memory_agent = MainMemoryAgent()

cfg = get_config_manager().get_section("server")

# ── API Key Auth ──
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


def verify_api_key(api_key: str = Depends(api_key_header)):
    expected = cfg.get("api_key", "")
    if not expected:
        logger.warning("API key not configured — authentication DISABLED")
        return ""  # no key configured — allow all (backward compat)
    if not api_key:
        raise HTTPException(status_code=403, detail="Missing API key header")
    if api_key != expected:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    return api_key


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
    project: str = "default"
    session_id: str = ""
    profile: str = "default"


class StoreRequest(BaseModel):
    user_id: str
    platform: Optional[str] = None
    task_id: str
    title: Optional[str] = None
    context: List[ContextMessage]
    task_status: str
    success: bool = False
    experience_summary: Optional[str] = None
    profile: str = "default"

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

EXCEPTION_RESPONSE = {"status": "error", "detail": "Internal server error"}


def _error_response(e: Exception, log_context: str = "") -> dict:
    """Unified error response — logs exception, returns generic message."""
    logger.error(f"{log_context}: {e}", exc_info=True)
    return {"status": "error", "detail": "Operation failed"}


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "detail": exc.detail},
    )


# ── Routes ──
@app.post("/api/memory/retrieve")
async def api_retrieve(req: RetrieveRequest, auth=Depends(verify_api_key)):
    try:
        result = memory_agent.retrieve_for_task(req.query, req.user_id, req.task_id, platform=req.platform, profile=req.profile)
        working = [
            {"source": m.source, "content": m.content,
             "importance": m.importance, "metadata": m.metadata}
            for m in result["working_memory"][:req.max_results]
        ]
        return {
            "working_memory": working,
            "experience_memory": result.get("raw_memory_sources", {}).get("experience", []),
            "knowledge_memory": result.get("raw_memory_sources", {}).get("knowledge", []),
            "confidence_score": result.get("confidence_score", 0.0),
            "used_weights": memory_agent.rl_optimizer.get_current_weights(),
            "feedback_requested": result.get("feedback_request", False),
            "raw_memory_sources": result.get("raw_memory_sources", {}),
            "task_features": result.get("task_features", {}),
        }
    except Exception as e:
            return _error_response(e, "api_retrieve")

@app.post("/api/memory/store")
async def api_store(req: StoreRequest, auth=Depends(verify_api_key)):
    try:
        ok = memory_agent.store(
            req.user_id, req.task_id,
            [{"role": m.role, "content": m.content} for m in req.context],
            req.task_status, req.success, req.experience_summary,
            platform=req.platform, title=req.title,
            profile=req.profile,
        )
        return {"status": "stored" if ok else "error", "user_id": req.user_id, "task_id": req.task_id}
    except Exception as e:
        return _error_response(e, "api_store")

@app.get("/api/memory/search-sessions")
async def search_sessions(q: str = "", user_id: str = None, project: str = None, limit: int = 5, auth=Depends(verify_api_key)):
    if not memory_agent or not memory_agent.is_persistence_enabled():
        return {"results": [], "message": "Persistence is not enabled"}
    try:
        results = memory_agent.db.search_transcripts(q, user_id, project, limit)
        return {"results": results, "count": len(results)}
    except Exception as e:
        logger.error("search_sessions: %s", e, exc_info=True)
        return {"results": [], "error": "Search failed"}

@app.post("/api/memory/feedback")
async def api_feedback(req: FeedbackRequest, auth=Depends(verify_api_key)):
    try:
        memory_agent.record_feedback(req.user_id, req.task_id, req.feedback, req.retrieved_memories)
        return {"status": "feedback_received", "user_id": req.user_id}
    except Exception as e:
        return _error_response(e, "api_feedback")

@app.post("/api/memory/sync-code")
async def api_sync_code(req: SyncCodeRequest, auth=Depends(verify_api_key)):
    try:
        memory_agent.sync_to_code_project(req.project_root, req.user_id)
        return {"status": "synced", "path": f"{req.project_root}/.echomind"}
    except Exception as e:
        return _error_response(e, "api_sync_code")

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
        return _error_response(e, "api_add_paper")

@app.post("/api/research/note")
async def api_add_note(req: ResearchNoteRequest, auth=Depends(verify_api_key)):
    try:
        note_id = memory_agent.add_research_note(
            user_id=req.user_id, topic=req.topic, content=req.content,
            linked_papers=req.linked_papers, tags=req.tags)
        return {"status": "stored", "note_id": note_id, "topic": req.topic}
    except Exception as e:
        return _error_response(e, "api_add_note")


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
        # Filter to requested IDs (if specified)
        if req.record_ids:
            id_set = set(req.record_ids)
            records = [r for r in full_records if r.get("id") in id_set]
            if not records:
                # Records may have been evicted; use placeholders
                records = [{"id": rid, "content": "", "text": ""} for rid in id_set]
        else:
            records = full_records
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
            "server": {k: v for k, v in cfg.get_section("server").items() if k != "api_key"},
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


# ── Delete API (O-9) ──


class DeleteRequest(BaseModel):
    memory_type: str
    memory_id: Optional[str] = None
    user_id: Optional[str] = None

@app.delete("/api/memory/{memory_type}/{memory_id}")
async def api_delete_memory(memory_type: str, memory_id: str, auth=Depends(verify_api_key)):
    try:
        deleted = memory_agent.db.delete_memory(memory_type, memory_id)
        return {"status": "deleted" if deleted else "not_found", "memory_type": memory_type, "memory_id": memory_id}
    except Exception as e:
        logger.error(f"api_delete_memory: {e}", exc_info=True)
        return {"status": "error", "detail": "Delete failed"}

@app.post("/api/memory/delete-user")
async def api_delete_user(req: DeleteRequest, auth=Depends(verify_api_key)):
    if not req.user_id:
        raise HTTPException(status_code=422, detail="user_id required")
    try:
        counts = memory_agent.db.delete_user_memories(req.user_id)
        return {"status": "deleted", "user_id": req.user_id, "counts": counts}
    except Exception as e:
        logger.error(f"api_delete_user: {e}", exc_info=True)
        return {"status": "error", "detail": "Delete failed"}

@app.post("/api/memory/cleanup")
async def api_cleanup(auth=Depends(verify_api_key)):
    try:
        ttl = {
            "context": 30,
            "task": 90,
            "experience": 180,
            "knowledge": 0,
        }
        counts = memory_agent.db.delete_expired(ttl)
        return {"status": "cleaned", "counts": counts}
    except Exception as e:
        logger.error(f"api_cleanup: {e}", exc_info=True)
        return {"status": "error", "detail": "Cleanup failed"}


# ── Memory Health ──
@app.get("/api/memory/health")
async def api_memory_health(auth=Depends(verify_api_key)):
    try:
        stats = memory_agent.db.get_memory_stats()
        return {"status": "ok", "stats": stats}
    except Exception as e:
        logger.error(f"api_memory_health: {e}", exc_info=True)
        return {"status": "error", "detail": "Health check failed"}

class StateRequest(BaseModel):
    state: str
    reason: str = ""

@app.post("/api/memory/{memory_type}/{memory_id}/state")
async def api_set_memory_state(memory_type: str, memory_id: str,
                                req: StateRequest, auth=Depends(verify_api_key)):
    try:
        memory_agent.db.save_memory_state(
            memory_type, memory_id, req.state, reason=req.reason, source="user")
        return {"status": "ok", "memory_type": memory_type, "memory_id": memory_id, "state": req.state}
    except Exception as e:
        logger.error(f"api_set_memory_state: {e}", exc_info=True)
        return {"status": "error", "detail": "State update failed"}


# ── Knowledge Evolution ──
@app.get("/api/knowledge/{knowledge_id}/evolution")
async def api_knowledge_evolution(knowledge_id: str, auth=Depends(verify_api_key)):
    try:
        rows = memory_agent.db._conn.execute(
            "SELECT * FROM knowledge_evolution WHERE source_id=? OR target_id=? ORDER BY created_at DESC",
            (knowledge_id, knowledge_id)
        ).fetchall()
        return {"knowledge_id": knowledge_id, "evolution": [dict(r) for r in rows]}
    except Exception as e:
        logger.error(f"api_knowledge_evolution: {e}", exc_info=True)
        return {"status": "error", "detail": "Evolution lookup failed"}


# ── MCP over HTTP (P3-1: Streamable HTTP MCP — JSON-RPC minimal viable) ──

try:
    from adapters.mcp_common import handle_mcp_request
    _MCP_AVAILABLE = True
except ImportError:
    _MCP_AVAILABLE = False

@app.post("/mcp")
async def mcp_endpoint(request: dict):
    import asyncio
    if not _MCP_AVAILABLE:
        return {"jsonrpc": "2.0", "error": {"code": -32603, "message": "MCP not available"}}
    try:
        return await asyncio.to_thread(handle_mcp_request, request)
    except Exception as e:
        logger.error(f"mcp_endpoint: {e}", exc_info=True)
        return {"jsonrpc": "2.0", "error": {"code": -32603, "message": str(e)}}

@app.get("/mcp")
async def mcp_handshake():
    return {"jsonrpc": "2.0", "result": {"protocolVersion": "2024-11-05"}}


# ── Entry ──
if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else cfg.get("port", 8005)
    host = cfg.get("host", "127.0.0.1")
    print(f"EchoMind Memory v{get_echomind_version()} — HTTP API Mode")
    print(f"  Endpoint: http://{host}:{port}")
    print(f"  Docs:     http://{host}:{port}/docs")
    uvicorn.run(app, host=host, port=port, log_level="info")