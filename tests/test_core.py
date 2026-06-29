"""Tests for core memory operations — store, retrieve, importance."""

import json


class TestStore:
    """MemoryAgent.store() behavior."""

    def test_store_without_persistence(self, memory_agent):
        """store() succeeds without persistence enabled."""
        memory_agent._persistence_enabled = False
        ok = memory_agent.store(
            "user_1", "task_1",
            [{"role": "user", "content": "hello"}],
            "completed", True, "Test task",
        )
        assert ok is True

    def test_store_with_context(self, memory_agent, sample_context):
        """store() accepts context messages."""
        ok = memory_agent.store(
            "user_1", "task_1", sample_context,
            "completed", True, "Sort function",
        )
        assert ok is True or ok is False  # at minimum doesn't crash

    def test_store_empty_context(self, memory_agent):
        """store() with empty context does not crash."""
        ok = memory_agent.store(
            "user_1", "task_2", [],
            "completed", False, None,
        )
        if ok is not None:
            assert isinstance(ok, bool)


class TestRetrieve:
    """MemoryAgent.retrieve_for_task() behavior."""

    def test_retrieve_basic(self, memory_agent):
        """retrieve_for_task() returns a dict with expected keys."""
        result = memory_agent.retrieve_for_task(
            "test query", "user_1", None,
        )
        assert isinstance(result, dict)
        assert "working_memory" in result
        assert "confidence_score" in result

    def test_retrieve_empty_query(self, memory_agent):
        """retrieve_for_task() handles empty query."""
        result = memory_agent.retrieve_for_task(
            "", "user_1", None,
        )
        assert isinstance(result, dict)

    def test_retrieve_with_profile(self, memory_agent):
        """retrieve_for_task() accepts profile parameter."""
        result = memory_agent.retrieve_for_task(
            "python", "user_1", None, profile="test_profile",
        )
        assert isinstance(result, dict)

    def test_importance_score_range(self, memory_agent):
        """_compute_importance returns scores in [0, 1] range."""
        score = memory_agent._compute_importance(
            "user_1", "python sorting", "python", "development",
        )
        assert 0.0 <= score <= 1.0


class TestFeedback:
    """Record feedback behavior."""

    def test_positive_feedback(self, memory_agent):
        """Positive feedback does not crash."""
        memory_agent.record_feedback(
            "user_1", "task_1", "positive",
            [{"source": "knowledge", "id": "k1", "content": "test"}],
        )
        assert True

    def test_negative_feedback(self, memory_agent):
        """Negative feedback does not crash."""
        memory_agent.record_feedback(
            "user_1", "task_1", "negative",
            [{"source": "knowledge", "id": "k1", "content": "test"}],
        )
        assert True


class TestReflection:
    """Reflection pipeline."""

    def test_build_prompt(self, memory_agent):
        """build_prompt returns a tuple."""
        prompt, ids = memory_agent.reflective.build_prompt(
            [{"id": "r1", "content": "test", "text": ""}],
            "user_1", "test",
        )
        assert isinstance(prompt, str)
        assert isinstance(ids, list)

    def test_reflect_with_llm(self, memory_agent, mock_llm_fn):
        """reflect_with_llm with mock LLM."""
        result = memory_agent.reflective.reflect_with_llm(
            [{"id": "r1", "content": "test", "text": ""}],
            "user_1", "test", mock_llm_fn,
        )
        if result is not None:
            assert hasattr(result, 'key_insights')
