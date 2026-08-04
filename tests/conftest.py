"""pytest fixtures for EchoMind Memory tests.

Usage:
    pip install pytest pytest-cov httpx
    pytest tests/ -v
"""

import os
import sys
import tempfile
import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timezone

import pytest

# Ensure project root is on sys.path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


@pytest.fixture
def tmp_db_path():
    """Provide a temporary SQLite database path."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    try:
        os.unlink(path)
        # Remove WAL and SHM files if they exist
        for ext in ("-wal", "-shm"):
            try:
                os.unlink(path + ext)
            except OSError:
                pass
    except OSError:
        pass


@pytest.fixture
def sqlite_store(tmp_db_path):
    """Create a fresh SqliteStore with temp DB."""
    from core.storage.sqlite_store import SqliteStore

    store = SqliteStore(db_path=tmp_db_path)
    store.connect()
    store.ensure_tables()
    return store


@pytest.fixture
def mock_llm_fn():
    """Return a simple mock LLM function."""

    def _llm(prompt: str) -> str:
        return json.dumps({
            "key_insights": ["test insight"],
            "user_preferences": {"response_style": "concise"},
            "procedural_rules": [],
            "new_knowledge": [{"content": "test knowledge", "domain": "general"}],
            "confidence": 0.8,
        })

    return _llm


@pytest.fixture
def memory_agent(tmp_db_path):
    """Create a MainMemoryAgent with temp DB and persistence enabled."""
    from core.memory_agent import MainMemoryAgent

    # Override config to use temp db path
    agent = MainMemoryAgent()
    agent.db.db_path = tmp_db_path
    agent.db.connect()
    agent.db.ensure_tables()
    agent._persistence_enabled = True
    return agent


@pytest.fixture
def sample_context():
    """Return a sample conversation context."""
    return [
        {"role": "user", "content": "Write a Python function to sort a list"},
        {"role": "assistant", "content": "Here's a sorting function using built-in sorted()"},
        {"role": "user", "content": "Use type hints please"},
        {"role": "assistant", "content": "Here's the typed version: def sort_list(items: list[int]) -> list[int]"},
    ]