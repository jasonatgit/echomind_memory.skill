"""Regression tests for the v1.2.21 post-v1.2.20 audit fixes.

Each test pins one defect found while auditing commit 7592eb8.
"""

import json


# ── P1-1: preferences must never be double-nested ─────────────────────────

def test_save_user_accepts_already_nested_preferences(sqlite_store):
    db = sqlite_store
    db.save_user("u1", preferences={"response_style": "concise"})
    nested = db._get_user_raw("u1", "default")["preferences"]
    assert nested == {"_default": {"response_style": "concise"}}

    # What echomind-cli used to pass: the in-memory nested shape, no platform.
    db.save_user("u1", preferences=nested)
    prefs = db._get_user_raw("u1", "default")["preferences"]
    assert prefs["_default"]["response_style"] == "concise"
    assert "_default" not in prefs["_default"]


def test_save_user_with_platform_keeps_flat_default(sqlite_store):
    db = sqlite_store
    db.save_user("u2", preferences={"response_style": "brief"},
                 platform="code_cli")
    prefs = db._get_user_raw("u2", "default")["preferences"]
    assert prefs["_default"]["response_style"] == "brief"
    assert prefs["code_cli"]["response_style"] == "brief"


# ── P1-2: trace rows must not consume the context recall budget ───────────

def test_search_context_excludes_trace_rows(memory_agent):
    db = memory_agent.db
    db.save_context("sess-turn", "u1",
                    [{"role": "user", "content": "hello"}],
                    platform="hermes")
    db.save_context("sess-trace", "u1", [], platform="hermes",
                    trace=json.dumps({"schema": "trace-v1"}))
    rows = db.search_context("u1", platform="hermes", limit=2)
    assert [r["session_id"] for r in rows] == ["sess-turn"]


# ── P1-3: Hermes v0.23.1 config schema translation ───────────────────────

def test_hermes_llm_sync_reads_model_default_and_env(monkeypatch):
    from core.hermes_llm_sync import parse_hermes_llm_config
    monkeypatch.setenv("HERMES_URL", "http://hermes.example/v1")
    monkeypatch.setenv("HERMES_KEY", "sk-test")
    conf = {
        "model": {
            "default": "deepseek-v4-pro",
            "base_url": "${HERMES_URL}",
            "provider": "custom:ustc",
        },
        "providers": {
            "ustc": {"api": "http://provider.example/v1",
                     "api_key": "${HERMES_KEY}", "model": "ignored"},
        },
    }
    overrides, provider = parse_hermes_llm_config(conf)
    assert provider == "custom:ustc"
    assert overrides["llm.model"] == "deepseek-v4-pro"
    assert overrides["llm.endpoint"] == "http://hermes.example/v1"
    assert overrides["llm.api_key"] == "sk-test"
    assert overrides["llm.provider"] == "openai_compatible"


def test_hermes_llm_sync_falls_back_to_provider_block(monkeypatch):
    from core.hermes_llm_sync import parse_hermes_llm_config
    monkeypatch.setenv("PROVIDER_URL", "http://provider.example/v1")
    conf = {
        "model": {"provider": "custom:local"},
        "providers": {"local": {"api": "${PROVIDER_URL}", "model": "m1"}},
    }
    overrides, _ = parse_hermes_llm_config(conf)
    assert overrides["llm.endpoint"] == "http://provider.example/v1"
    assert overrides["llm.model"] == "m1"


def test_hermes_llm_sync_rejects_non_openai_provider():
    from core.hermes_llm_sync import parse_hermes_llm_config
    assert parse_hermes_llm_config(
        {"model": {"default": "claude", "provider": "anthropic"}}) is None
    assert parse_hermes_llm_config({}) is None


# ── P2-1/P2-5/P2-4: provider hooks are config-derived / save is robust ────

def test_identity_signature_reads_config(tmp_path, monkeypatch):
    from adapters.hermes_provider import EchomindMemoryProvider
    cfg_file = tmp_path / "echomind_config.yaml"
    cfg_file.write_text(
        "db:\n  path: /tmp/sig.db\ndefault_user: sig-user\n",
        encoding="utf-8")
    monkeypatch.setenv("ECHOMIND_CONFIG", str(cfg_file))
    sig = EchomindMemoryProvider().identity_signature()
    assert sig["echomind.db_path"] == "/tmp/sig.db"
    assert sig["echomind.user_id"] == "sig-user"
    assert "echomind.config_mtime" in sig


def test_save_config_scalar_db_keeps_api_key(tmp_path, monkeypatch):
    import yaml
    from adapters.hermes_provider import EchomindMemoryProvider
    cfg_file = tmp_path / "echomind_config.yaml"
    cfg_file.write_text("db: /legacy/path.db\n", encoding="utf-8")
    monkeypatch.setenv("ECHOMIND_CONFIG", str(cfg_file))
    EchomindMemoryProvider().save_config(
        {"api_key": "secret-key", "db_path": "/new/path.db"}, str(tmp_path))
    data = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    assert data["server"]["api_key"] == "secret-key"
    assert data["db"]["path"] == "/new/path.db"
    assert (cfg_file.stat().st_mode & 0o777) == 0o600


# ── P2-7/P2-8/P3: fallback coercion, LLM client guards, score clamp ───────

def test_fallback_string_confidence_is_coerced():
    from core._reflective_fallback import _process_reflection
    raw = json.dumps({"key_insights": ["x"], "confidence": "0.1"})
    # Before the fix the string compare raised TypeError; the caller then
    # silently downgraded the whole LLM reflection to keyword extraction.
    assert _process_reflection(
        raw, [], "u", "p", {"min_confidence": 0.65}, {}, None) is None


def test_parse_score_accepts_out_of_range_decimal():
    from core.llm_client import LLMClient
    assert LLMClient._parse_score("10.5") == 1.0
    assert LLMClient._parse_score("8/10") == 0.8


def test_resolve_api_key_and_endpoint_guards(monkeypatch):
    from core.llm_client import LLMClient
    assert LLMClient._resolve_api_key({"api_key": None}) == ""
    monkeypatch.setenv("ECHOMIND_TEST_ENDPOINT", "http://llm.example/v1")
    client = LLMClient({
        "provider": "openai_compatible",
        "endpoint": "${ECHOMIND_TEST_ENDPOINT}",
        "model": "m",
    })
    assert client._endpoint == "http://llm.example/v1"


def test_safe_bool_string_false():
    from adapters.mcp_common import _safe_bool
    assert _safe_bool("false") is False
    assert _safe_bool("true") is True
    assert _safe_bool(False) is False
    assert _safe_bool(None, default=True) is True


def test_evict_oldest_clears_summary_index():
    from core.agents.experience_agent import ExperienceMemoryAgent
    agent = ExperienceMemoryAgent()
    agent.MAX_ITEMS = 2
    for summary in ("summary one", "summary two", "summary three"):
        agent.store_experience("u", "t", "code_review", True, ["s"], summary)
    assert len(agent.store) == 1
    assert len(agent._summary_index) == len(agent.store)
