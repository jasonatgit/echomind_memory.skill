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
