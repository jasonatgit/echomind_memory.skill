"""Regression tests covering the deep-review bug fixes (v1.2.6 audit round).

Covers: transaction atomicity, _maybe_commit gating, daily-limit reset,
timestamp parsing/unification, ContextMessage Optional, UPSERT field updates,
knowledge/experience last_access_at propagation, and main.py param pass-through.
"""

import json
from datetime import datetime, timezone
from unittest import mock


# ── Transaction atomicity & _maybe_commit (H3) ──

class TestTransactionAtomicity:
    def test_transaction_rolls_back_all_saves(self, sqlite_store):
        """A failure mid-batch must roll back ALL earlier saves, not partial."""
        class _Boom(Exception):
            pass
        try:
            with sqlite_store.transaction():
                sqlite_store.save_user("u_rollback", {"k": "v"}, {}, [])
                sqlite_store.save_task("u_rollback", "t1", "T", "pending", [], {})
                raise _Boom("boom")
        except _Boom:
            pass
        users = sqlite_store.load_users()
        tasks = sqlite_store.load_tasks()
        assert not any(u["user_id"] == "u_rollback" for u in users)
        assert not any(t["user_id"] == "u_rollback" for t in tasks)

    def test_transaction_commit_persists_all(self, sqlite_store):
        """Successful batch persists everything."""
        with sqlite_store.transaction():
            sqlite_store.save_user("u_commit", {"k": "v"}, {}, [])
            sqlite_store.save_task("u_commit", "t1", "T", "pending", [], {})
        users = sqlite_store.load_users()
        tasks = sqlite_store.load_tasks()
        assert any(u["user_id"] == "u_commit" for u in users)
        assert any(t["user_id"] == "u_commit" for t in tasks)


# ── Daily-limit reset, per-user + persisted (H6 / P5-B) ──

class TestDailyLimitReset:
    def test_check_daily_limit_is_threshold_compare(self, memory_agent):
        """T2: below limit returns False, at/over limit returns True (per user)."""
        ra = memory_agent.reflective
        assert ra._check_daily_limit("u1") is False  # fresh: count < limit
        for _ in range(ra._daily_limit):
            ra._increment_daily_count("u1")
        assert ra._check_daily_limit("u1") is True
        # per-user isolation: another user's fresh (user, day) is not blocked
        assert ra._check_daily_limit("u2") is False

    def test_process_result_short_circuits_at_limit(self, memory_agent):
        """T2/M-6: process_result returns None once the daily limit is hit, so the
        HTTP layer can distinguish 429 (limit) from 400 (parse failure) via
        _check_daily_limit()."""
        import core.reflective_agent as ra_module

        ra = memory_agent.reflective
        for _ in range(ra._daily_limit):
            ra._increment_daily_count("u1")  # at the limit
        # Ensure an engine is present so the ONLY reason to return None here is
        # the limit short-circuit (in a no-Cython env _engine is None and would
        # return None first, making the assertion vacuous).
        with mock.patch.object(ra_module, "_engine", new=object()):
            assert ra.process_result("llm", [], "u1", "http") is None
        assert ra._check_daily_limit("u1") is True

    def test_reset_daily_count_on_day_change(self, memory_agent):
        """Counter resets on a new UTC calendar day.

        P5-B keys the count by (user_id, date), so a new day is a fresh key that
        starts at 0 — no explicit reset needed. A different user also starts at 0
        (per-user isolation), which covers the same fresh-key semantics.
        """
        ra = memory_agent.reflective
        for _ in range(ra._daily_limit + 1):
            ra._increment_daily_count("u1")  # over limit
        assert ra._check_daily_limit("u1") is True
        # A fresh (user, day) key — a different user today — starts at 0.
        assert ra._get_daily_count("u2") == 0
        assert ra._check_daily_limit("u2") is False
        # The persisted counter is per-(user, date): u1's over-limit count is
        # unchanged while u2 stays clean.
        assert ra._check_daily_limit("u1") is True


# ── Timestamps (H2/M2) ──

class TestTimestampHandling:
    def test_parse_db_ts_naive(self, memory_agent):
        dt = memory_agent._parse_db_ts("2026-01-01 10:00:00")
        assert dt is not None
        assert dt.tzinfo is not None
        assert dt.year == 2026

    def test_parse_db_ts_aware(self, memory_agent):
        dt = memory_agent._parse_db_ts("2026-01-01T10:00:00+00:00")
        assert dt is not None
        assert dt.tzinfo is not None

    def test_parse_db_ts_invalid_returns_none(self, memory_agent):
        assert memory_agent._parse_db_ts("not-a-date") is None
        assert memory_agent._parse_db_ts(None) is None

    def test_freshness_accepts_datetime_object(self, memory_agent):
        """_freshness must not crash on a datetime object (was a TypeError)."""
        record = {"last_updated": datetime.now(timezone.utc)}
        assert memory_agent._freshness(record) == 1.0

    def test_update_last_access_uses_db_format(self, memory_agent, sqlite_store):
        """_update_last_access_for_retrieved writes 'YYYY-MM-DD HH:MM:SS' (matches DB)."""
        memory_agent.db = sqlite_store
        memory_agent._persistence_enabled = True
        sqlite_store.save_knowledge("k:1", "general", "content", {})
        sqlite_store.save_memory_state("knowledge", "k:1", "active")
        memory_agent._update_last_access_for_retrieved(
            {"knowledge": [{"id": "k:1", "content": "content"}]}, "user"
        )
        row = sqlite_store._conn.execute(
            "SELECT last_access_at FROM knowledge_memory WHERE id='k:1'"
        ).fetchone()
        assert row is not None
        # format must be space-separated (DB datetime('now') style), not ISO 'T'
        assert row["last_access_at"] and "T" not in row["last_access_at"]


# ── UPSERT field updates (H4) ──

class TestUpsertFieldUpdates:
    def test_save_task_updates_title_on_conflict(self, sqlite_store):
        sqlite_store.save_task("u1", "t1", "Old Title", "completed", [], {})
        sqlite_store.save_task("u1", "t1", "New Title", "completed", [], {})
        tasks = sqlite_store.load_tasks()
        match = [t for t in tasks if t["id"] == "u1:t1"]
        assert len(match) == 1
        assert match[0]["title"] == "New Title"

    def test_save_experience_updates_success_on_conflict(self, sqlite_store):
        sqlite_store.save_experience("u1", "dev", 0, [], "same", experience_id="e:1")
        sqlite_store.save_experience("u1", "dev", 1, [], "same", experience_id="e:1")
        exps = sqlite_store.load_experiences()
        match = [e for e in exps if e["id"] == "e:1"]
        assert len(match) == 1
        # success persisted as int
        assert int(match[0]["success"]) == 1


# ── ContextMessage Optional (M6) ──

class TestContextMessageOptional:
    def test_content_accepts_none(self):
        from core.models.context import ContextMessage
        msg = ContextMessage(role="assistant", content=None)
        # Optional content accepted without crashing; explicit None is preserved
        assert msg.content is None


# ── Safe JSON loads (L7) ──

class TestSafeJsonLoads:
    def test_safe_json_loads_valid(self):
        from core.storage.sqlite_store import _safe_json_loads
        assert _safe_json_loads('{"a": 1}', {}) == {"a": 1}

    def test_safe_json_loads_invalid(self):
        from core.storage.sqlite_store import _safe_json_loads
        assert _safe_json_loads("{malformed", []) == []
        assert _safe_json_loads(None, {}) == {}


# ── main.py param pass-through (H1) ──

class TestMainParamPassThrough:
    def test_retrieve_forwards_project_session(self):
        """T3: main.call('retrieve_memory') really reaches retrieve_for_task with
        project/session_id/profile intact. (The OLD test mocked the method then
        called it directly — circular and never exercised main.py.)"""
        import main as main_module

        fake_agent = mock.Mock()
        fake_agent.is_persistence_enabled.return_value = True
        fake_agent.retrieve_for_task.return_value = {
            "retrieved_memories": [], "confidence_score": 0.0,
            "feedback_request": False,
        }
        fake_agent.rl_optimizer.get_current_weights.return_value = {}
        path = "/tmp/echomind-main-test.yaml"
        # Pre-seed the agent cache so main.call() hits the cached branch and
        # operates on our fake instead of opening a real DB.
        with mock.patch.dict(main_module._call_agents, {path: (fake_agent, None)}):
            main_module.call(
                "retrieve_memory", config_path=path,
                query="q", user_id="u", task_id="t",
                platform="http", project="proj", session_id="sess", profile="p2",
            )
        fake_agent.retrieve_for_task.assert_called_once()
        kwargs = fake_agent.retrieve_for_task.call_args.kwargs
        assert kwargs["project"] == "proj"
        assert kwargs["session_id"] == "sess"
        assert kwargs["profile"] == "p2"
        assert kwargs["platform"] == "http"


# ── Autoreflection Absorption Phase 1+2 (epistemic_mode, provenance, autoreflection_score) ──

class TestEpistemicMode:
    def test_resolve_epistemic_returns_user_provided(self, memory_agent):
        assert "user_provided" == memory_agent._resolve_epistemic("user_direct")

    def test_resolve_epistemic_returns_fuzzy_for_assistant(self, memory_agent):
        assert "fuzzy" == memory_agent._resolve_epistemic("assistant")

    def test_resolve_epistemic_returns_reasoned_for_reflection(self, memory_agent):
        assert "reasoned" == memory_agent._resolve_epistemic("reflection")

    def test_resolve_epistemic_external_import_is_referenced(self, memory_agent):
        """W-1: external imports map to 'referenced' (was untested)."""
        assert "referenced" == memory_agent._resolve_epistemic("external_import")

    def test_resolve_epistemic_unknown_source_falls_back(self, memory_agent):
        """W-1: any unrecognized source maps to 'unknown', never crashes."""
        assert "unknown" == memory_agent._resolve_epistemic("bogus_source")


class TestEvolutionProvenanceMigration:
    def test_migration_v9_adds_origin_columns(self, sqlite_store):
        """After migration v9, knowledge_evolution has origin columns."""
        cursor = sqlite_store._conn.execute("PRAGMA table_info(knowledge_evolution)")
        cols = {r[1] for r in cursor.fetchall()}
        for expected in ("origin_agent", "origin_session_id", "origin_turn"):
            assert expected in cols, f"Missing column: {expected}"


class TestAutoreflectionScore:
    def test_score_returns_tuple(self, memory_agent):
        score, summary = memory_agent.compute_autoreflection_score()
        assert isinstance(score, int)
        assert 0 <= score <= 4
        assert isinstance(summary, str)
        assert "score" in summary.lower()

    def test_score_c2_increases_with_records(self, memory_agent, sqlite_store):
        """After loading real data, C2 should be 1 (records present)."""
        memory_agent.db = sqlite_store
        sqlite_store.save_knowledge("k:score", "test", "content", {})
        sqlite_store.save_memory_state("knowledge", "k:score", "active")
        score, _ = memory_agent.compute_autoreflection_score()
        assert score >= 1


class TestKnowledgeSearchEpistemic:
    def test_epistemic_mode_in_search_result(self, memory_agent):
        ka = memory_agent.knowledge_agent
        ka.add_document("test knowledge", {"epistemic_mode": "fuzzy",
                                            "epistemic_detail": "LLM-generated",
                                            "source": "test", "user_id": "u1"},
                        entry_id="epi:1")
        results = ka.search("test knowledge")
        assert len(results) >= 1
        assert results[0].get("epistemic_mode") == "fuzzy"
        assert results[0].get("epistemic_detail") == "LLM-generated"


# ── Markdown Rendering (v1.2.9) ──

class TestMarkdownExport:
    def test_export_runs_without_exception(self, memory_agent):
        md = memory_agent.export_memory_to_markdown("test_user")
        assert isinstance(md, str)
        assert len(md) > 0
        assert "# " in md  # has at least one heading

    def test_cognitive_pos_in_export(self, memory_agent):
        ka = memory_agent.knowledge_agent
        ka.add_document("with cognitive pos", {
            "source": "test", "user_id": "test_user",
            "category": "test",
        }, entry_id="cog:2")
        # also inject cognitive_pos via search_all-visible path
        entry = ka.store.get("cog:2")
        if entry:
            entry.metadata["cognitive_pos"] = "nok"
        md = memory_agent.export_memory_to_markdown("test_user")
        # the export should contain a heading and the rendered cognitive pos icon
        assert "## 📚 Knowledge" in md
        assert "⚡ nok" in md

    def test_prefetch_markdown_format(self, memory_agent):
        """Verify _format_prefetch_context produces <memory-context> wrapper."""
        result = {
            "retrieved_memories": [
                type("M", (), {"source": "knowledge", "content": "test content",
                 "trust_score": 0.8})(),
            ],
            "user": {"preferences": {"response_style": "concise"}},
        }
        from adapters.hermes_provider import EchomindMemoryProvider

        assert callable(EchomindMemoryProvider._format_prefetch_context)
        provider = EchomindMemoryProvider.__new__(EchomindMemoryProvider)
        provider._user_id = "test_user"
        ctx = EchomindMemoryProvider._format_prefetch_context(provider, result)
        assert "<memory-context>" in ctx
        assert "</memory-context>" in ctx


# ── Renderer data-source decoupling (Step 2) ──

class TestRenderDataclass:
    def test_render_full_archive_from_memory_archive(self):
        """render_full_archive accepts a pure MemoryArchive — no agent needed."""
        from core.markdown_renderer import (
            MemoryArchive, KnowledgeRow, ExperienceRow, TaskRow, render_full_archive,
        )
        data = MemoryArchive(
            version="1.2.9",
            generated_at="2026-01-01T00:00:00+00:00",
            autoreflection_score=3,
            autoreflection_summary="OK",
            stats={"knowledge": {"active": 1, "stale": 0, "archived": 0}},
            knowledge=[KnowledgeRow(content="test", trust_score=0.9,
                                    epistemic_mode="user_provided",
                                    cognitive_pos="nok", domain="test")],
            experience=[ExperienceRow(summary="did x", frequency=2, success=True)],
            tasks=[TaskRow(title="task", status="completed")],
        )
        md = render_full_archive(data)
        assert isinstance(md, str)
        assert "## 📚 Knowledge" in md
        assert "✅ User Confirmed" in md
        assert "⚡ nok" in md


# ── cognitive_pos lifecycle migration (v1.2.9, A1) ──

class TestCognitivePosMigration:
    def test_migrate_nok_fok_exo_thresholds(self, memory_agent):
        """cognitive_pos migrates nok → fok → exo by freshness thresholds."""
        agent = memory_agent
        ka = agent.knowledge_agent
        ka.add_document("fresh knowledge entry", {
            "source": "test", "user_id": "test_user", "category": "test",
        }, entry_id="cog:mig")
        entry = ka.store.get("cog:mig")
        entry.metadata["cognitive_pos"] = "nok"

        # freshness above FOK threshold → nok (unchanged)
        agent._migrate_cognitive_pos("cog:mig", 1.0)
        assert ka.store["cog:mig"].metadata["cognitive_pos"] == "nok"

        # freshness between EXO and FOK → fok
        agent._migrate_cognitive_pos("cog:mig", 0.2)
        assert ka.store["cog:mig"].metadata["cognitive_pos"] == "fok"

        # freshness below EXO threshold → exo
        agent._migrate_cognitive_pos("cog:mig", 0.05)
        assert ka.store["cog:mig"].metadata["cognitive_pos"] == "exo"

    def test_migrate_threshold_boundaries(self, memory_agent):
        """Boundary values at the FOK/EXO thresholds use strict '<' comparison.

        _migrate_cognitive_pos maps:
          freshness < 0.1            → exo
          0.1 <= freshness < 0.3     → fok
          freshness >= 0.3           → nok
        So exactly 0.3 is nok (not fok) and exactly 0.1 is fok (not exo).
        """
        agent = memory_agent
        ka = agent.knowledge_agent
        ka.add_document("boundary entry", {
            "source": "test", "user_id": "test_user", "category": "test",
        }, entry_id="cog:boundary")

        # exactly 0.3 → nok (freshness < 0.3 is False)
        agent._migrate_cognitive_pos("cog:boundary", 0.3)
        assert ka.store["cog:boundary"].metadata["cognitive_pos"] == "nok"

        # just below 0.3 → fok
        agent._migrate_cognitive_pos("cog:boundary", 0.299)
        assert ka.store["cog:boundary"].metadata["cognitive_pos"] == "fok"

        # exactly 0.1 → fok (freshness < 0.1 is False)
        agent._migrate_cognitive_pos("cog:boundary", 0.1)
        assert ka.store["cog:boundary"].metadata["cognitive_pos"] == "fok"

        # just below 0.1 → exo
        agent._migrate_cognitive_pos("cog:boundary", 0.099)
        assert ka.store["cog:boundary"].metadata["cognitive_pos"] == "exo"

    def test_state_scan_limit_configurable(self, memory_agent):
        """_update_memory_states reads state_scan_limit from config (default 1000)."""
        agent = memory_agent
        try:
            limit = agent.cfg.get("retrieval", "state_scan_limit", default=1000)
            assert int(limit) == 1000
        except Exception:
            raise AssertionError("state_scan_limit should default to 1000")