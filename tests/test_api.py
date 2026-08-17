"""Tests for HTTP API endpoints."""

import json
from fastapi.testclient import TestClient
import pytest

# Build the test app
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.http_api import app
from core.config_manager import get_config_manager


@pytest.fixture
def client():
    return TestClient(app)


class TestHealth:
    """Health check endpoint."""

    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_health_has_storage(self, client):
        resp = client.get("/health")
        data = resp.json()
        assert data["storage"] == "sqlite"


class TestApiKey:
    """API key authentication."""

    def test_no_key_still_allowed(self, client):
        """When no api_key configured, requests should be allowed."""
        cfg = get_config_manager().get_section("server")
        if not cfg.get("api_key"):
            resp = client.get("/api/config")
            assert resp.status_code == 200
        else:
            pytest.skip("api_key is configured in this environment")


class TestConfig:
    """Config endpoints."""

    def test_get_config_contains_sections(self, client):
        resp = client.get("/api/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "sections" in data
        # api_key should be filtered
        llm = data["sections"].get("llm", {})
        assert "api_key" not in llm

    def test_get_config_has_config_path(self, client):
        resp = client.get("/api/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "config_path" in data


class TestRetrieveEndpoint:
    """Retrieve API endpoint."""

    def test_retrieve_returns_expected_structure(self, client):
        resp = client.post("/api/memory/retrieve", json={
            "user_id": "test_user",
            "query": "python",
            "max_results": 3,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "working_memory" in data
        assert "confidence_score" in data

    def test_retrieve_without_user_id(self, client):
        resp = client.post("/api/memory/retrieve", json={
            "query": "python",
        })
        assert resp.status_code in (200, 422)


class TestStoreEndpoint:
    """Store API endpoint."""

    def test_store_minimal(self, client):
        resp = client.post("/api/memory/store", json={
            "user_id": "test_user",
            "task_id": "test_task",
            "context": [{"role": "user", "content": "hello"}],
            "task_status": "completed",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data


class TestReflectDailyLimit:
    """Regression for audit HIGH-1: the HTTP reflect endpoint must return 429
    when the per-user daily limit is hit, not a 500 from a missing argument.

    P5-B made _check_daily_limit(user_id) per-user; http_api.py previously
    called it without args on the daily-limit path (api_reflect's output is
    None branch), raising TypeError -> HTTP 500 instead of the intended 429.
    """

    def test_daily_limit_hit_returns_429_not_500(self, client, monkeypatch):
        import adapters.http_api as http_api_mod

        ra = http_api_mod.memory_agent.reflective
        # Force the daily-limit path: process_result returns None (as it does
        # on both limit-reached and parse-failure), and the limit check returns
        # True. Set as instance attributes so the endpoint's calls hit these.
        monkeypatch.setattr(ra, "process_result", lambda **kw: None)
        monkeypatch.setattr(ra, "_check_daily_limit", lambda user_id: True)

        resp = client.post("/api/reflect", json={
            "user_id": "audit_u",
            "llm_response": "{}",
        })
        # With the fix the limit branch raises HTTPException(429); the 500
        # would previously fire from the missing-arg TypeError.
        assert resp.status_code == 429

    def test_parse_failure_returns_400(self, client, monkeypatch):
        """M-6: when the limit is NOT hit, a parse failure stays a 400."""
        import adapters.http_api as http_api_mod

        ra = http_api_mod.memory_agent.reflective
        monkeypatch.setattr(ra, "process_result", lambda **kw: None)
        monkeypatch.setattr(ra, "_check_daily_limit", lambda user_id: False)

        resp = client.post("/api/reflect", json={
            "user_id": "audit_u",
            "llm_response": "{}",
        })
        assert resp.status_code == 400
