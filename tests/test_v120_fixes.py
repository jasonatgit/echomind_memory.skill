"""Regression tests for the v1.2.20 audit + Hermes v0.23.1 adaptation fixes.

Each test pins one defect that was verified against the source tree; see the
matching finding in the v1.2.20 changelog (P1-*, P2-*, P3-*, H*).
"""

import os

from core.storage.sqlite_store import stable_memory_key


# ── P1-1: globally-shared ("default") knowledge is retrievable by a user ──

def test_knowledge_default_tenant_visible_to_user():
    from core.agents.knowledge_agent import KnowledgeMemoryAgent
    a = KnowledgeMemoryAgent()
    a.add_document("shared global fact about docker", {"user_id": "default"})
    a.add_document("jason own fact about python", {"user_id": "jason"})
    results = a.search("docker fact", user_id="jason", top_k=10)
    contents = [r["content"] for r in results]
    assert "shared global fact about docker" in contents


# ── P1-2: bulk deletes purge the in-memory fast path ──

def test_delete_user_memories_purges_memory(memory_agent):
    db = memory_agent.db
    db.save_knowledge("k:v120", "general", "some durable content", {},
                      user_id="u1")
    memory_agent._reset_memory_agents()
    memory_agent._load_from_db()
    assert "k:v120" in memory_agent.knowledge_agent.store

    memory_agent.delete_user_memories("u1")
    assert "k:v120" not in memory_agent.knowledge_agent.store
    assert db.search_knowledge_by_content("some durable content", user_id="u1") is None


def test_cleanup_expired_purges_memory(memory_agent):
    db = memory_agent.db
    db.save_knowledge("k:old", "general", "stale content", {}, user_id="u2")
    db._conn.execute(
        "UPDATE knowledge_memory SET updated_at='2000-01-01 00:00:00', "
        "last_access_at='2000-01-01 00:00:00' WHERE id='k:old'")
    memory_agent._reset_memory_agents()
    memory_agent._load_from_db()
    assert "k:old" in memory_agent.knowledge_agent.store

    memory_agent.cleanup_expired({"knowledge": 1})
    assert "k:old" not in memory_agent.knowledge_agent.store


# ── P1-3: reflection with >8 insights is not discarded ──

def test_reflection_output_accepts_many_insights():
    from core.models.reflection import ReflectionOutput
    out = ReflectionOutput(key_insights=[f"i{i}" for i in range(10)], confidence=0.8)
    assert len(out.key_insights) == 10


def test_reflection_sanitizer_trims_key_insights():
    from core.reflective_agent import ReflectiveAgent
    clean = ReflectiveAgent._sanitize_output_dict({
        "key_insights": [f"i{i}" for i in range(20)],
        "confidence": 1.7,
        "importance_scores": {"a": 1},
    })
    assert len(clean["key_insights"]) == 8
    assert clean["confidence"] == 1.0


# ── P2-1/P2-2: task status + original task_id survive a reload ──

def test_task_status_and_task_id_persist(memory_agent):
    user_id = "taskuser"
    raw_task_id = "tidv120"
    ok = memory_agent.store(
        user_id, raw_task_id,
        [{"role": "user", "content": "do a thing"},
         {"role": "assistant", "content": "done a thing"}],
        task_status="completed", success=True,
        extract_knowledge=False,
    )
    assert ok

    key = stable_memory_key(user_id, raw_task_id)
    assert memory_agent.task_agent.store[key].status == "completed"

    memory_agent._reset_memory_agents()
    memory_agent._load_from_db()
    task = memory_agent.task_agent.store[key]
    assert task.status == "completed"
    assert task.task_id == raw_task_id
    assert memory_agent.task_agent.get_recent_tasks(user_id)[0]["task_id"] == raw_task_id


# ── P2-3/P2-9: access_count + trust_score are restored into memory ──

def test_access_count_and_trust_reload(memory_agent):
    db = memory_agent.db
    db.save_knowledge("k:trust", "general", "trusted content", {},
                      trust_score=0.9, user_id="u3")
    db._conn.execute("UPDATE knowledge_memory SET access_count=7 WHERE id='k:trust'")
    memory_agent._reset_memory_agents()
    memory_agent._load_from_db()
    entry = memory_agent.knowledge_agent.store["k:trust"]
    assert entry.metadata["access_count"] == 7
    assert entry.metadata["trust_score"] == 0.9


# ── P2-5: C2 no longer crashes on scalar growth keys ──

def test_autoreflection_c2_counts_active(memory_agent):
    memory_agent.db.save_knowledge("k:c2", "general", "c2 content", {}, user_id="u4")
    memory_agent.db.save_memory_state("knowledge", "k:c2", "active")
    _score, summary = memory_agent.compute_autoreflection_score()
    assert "✅ C2" in summary


# ── P2-8: extract_knowledge=False skips knowledge extraction ──

def test_extract_knowledge_false_skips_knowledge(memory_agent):
    user_id = "nokbuser"
    before = memory_agent.db._conn.execute(
        "SELECT COUNT(*) FROM knowledge_memory WHERE user_id=?", (user_id,)).fetchone()[0]
    ok = memory_agent.store(
        user_id, "t-nokb",
        [{"role": "user", "content": "hi"},
         {"role": "assistant", "content": "a fairly long assistant reply that "
                                          "would otherwise become knowledge"}],
        task_status="completed", success=True, extract_knowledge=False,
    )
    assert ok
    after = memory_agent.db._conn.execute(
        "SELECT COUNT(*) FROM knowledge_memory WHERE user_id=?", (user_id,)).fetchone()[0]
    assert after == before


# ── P3-1: malformed habits JSON falls back to a dict, not a list ──

def test_load_users_malformed_habits_is_dict(memory_agent):
    memory_agent.db._conn.execute(
        "INSERT INTO user_memory (user_id, profile, preferences, habits, history) "
        "VALUES ('badhabits', 'default', '{}', 'not-json', '[]')")
    users = memory_agent.db.load_users()
    row = next(u for u in users if u["user_id"] == "badhabits")
    assert row["habits"] == {}


# ── P3-2: score parser ignores unrelated numbers ──

def test_parse_score_boundaries():
    from core.llm_client import LLMClient
    assert LLMClient._parse_score("8/10") == 0.8
    assert LLMClient._parse_score("10") == 1.0
    assert LLMClient._parse_score("The year is 2024") == 0.0


# ── P3-3: summary-only transcript keeps user_id ──

def test_transcript_summary_persists_user_id(memory_agent):
    db = memory_agent.db
    db.save_transcript_summary("sess-v120", "hello summary world", user_id="u5")
    rows = db.search_transcripts("hello", user_id="u5")
    assert any(r["session_id"] == "sess-v120" for r in rows)


# ── P2-10: transaction lock is released when BEGIN fails ──

def test_transaction_lock_released_on_begin_failure(sqlite_store):
    store = sqlite_store
    store._conn.execute("BEGIN")
    try:
        try:
            with store.transaction():
                pass
        except Exception:
            pass
        # RLock must not still be held after the failed __enter__.
        assert store._lock._is_owned() is False
    finally:
        store._conn.rollback()


# ── H1: per-instance LLM clients do not mutate the global singleton ──

def test_new_llm_client_is_isolated():
    import core.llm_client as lc
    lc._client_singleton = None
    c1 = lc.new_llm_client({"provider": "openai_compatible",
                            "endpoint": "http://a.example/v1", "model": "m"})
    c2 = lc.new_llm_client({"provider": "openai_compatible",
                            "endpoint": "http://b.example/v1", "model": "m"})
    assert c1 is not None and c2 is not None
    assert c1 is not c2
    assert c1._endpoint != c2._endpoint
    assert lc._client_singleton is None


def test_get_llm_client_with_config_does_not_replace_singleton():
    import core.llm_client as lc
    lc._client_singleton = None
    lc.get_llm_client({"provider": "openai_compatible",
                       "endpoint": "http://c.example/v1", "model": "m"})
    assert lc._client_singleton is None


# ── H7: env-var expansion for secrets ──

def test_expand_env_value(monkeypatch):
    from core.config_manager import expand_env_value
    monkeypatch.setenv("ECHOMIND_TEST_KEY", "sekret")
    assert expand_env_value("${ECHOMIND_TEST_KEY}") == "sekret"
    assert expand_env_value("${ECHOMIND_MISSING_KEY}", "dflt") == "dflt"
    assert expand_env_value("plain-value") == "plain-value"


# ── H5/H6: provider exposes the v0.23.1 hooks ──

def test_provider_optional_hooks_present():
    from adapters.hermes_provider import EchomindMemoryProvider
    p = EchomindMemoryProvider()
    assert p.name == "echomind"
    assert p.identity_signature()["echomind.profile"] == "default"
    assert p.recall_status() is None
    assert p.unavailable_reason() == ""
