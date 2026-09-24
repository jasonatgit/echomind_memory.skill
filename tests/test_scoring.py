"""Unit tests for the extracted pure scoring / novelty helpers (v1.2.18).

These functions previously lived on MainMemoryAgent and had ZERO direct test
coverage (the v1.2.15/1.2.17 GSPO + scoring bug hot spots). Extracting them to
core/scoring.py and core/lang_novelty.py makes them independently testable —
the primary payoff of the P1 refactor.
"""

from datetime import datetime, timedelta, timezone

from core.models.memory_record import MemoryRecord
from core import scoring
from core import lang_novelty


class _Cfg:
    """Minimal cfg stub exposing the nested get() used by freshness()."""

    def __init__(self, data=None):
        self._data = data or {}

    def get(self, section, key, default=None):
        return self._data.get(section, {}).get(key, default)


# ── score_base ──

class TestScoreBase:
    def test_weighted_average_normalizes_by_used_weight(self):
        # (1.0*0.5 + 0.5*0.5) / (0.5+0.5) = 0.75
        assert scoring.score_base([(1.0, 0.5), (0.5, 0.5)]) == 0.75

    def test_empty_terms_is_zero(self):
        assert scoring.score_base([]) == 0.0

    def test_zero_weight_sum_is_zero(self):
        assert scoring.score_base([(1.0, 0.0)]) == 0.0

    def test_boosts_applied_and_capped_at_one(self):
        assert scoring.score_base([(0.6, 1.0)], boosts=[1.3]) == 0.78
        assert scoring.score_base([(0.9, 1.0)], boosts=[1.3, 1.3]) == 1.0

    def test_missing_dims_do_not_shrink_base(self):
        # a source carrying only one dim must still be able to reach ~1.0
        assert scoring.score_base([(1.0, 0.1)]) == 1.0


# ── parse_db_ts ──

class TestParseDbTs:
    def test_none_and_empty(self):
        assert scoring.parse_db_ts(None) is None
        assert scoring.parse_db_ts("") is None
        assert scoring.parse_db_ts("   ") is None

    def test_sqlite_format_becomes_aware_utc(self):
        dt = scoring.parse_db_ts("2026-01-02 03:04:05")
        assert dt is not None and dt.tzinfo is not None
        assert dt.year == 2026 and dt.hour == 3

    def test_aware_datetime_passthrough(self):
        src = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert scoring.parse_db_ts(src) == src

    def test_naive_datetime_gets_utc(self):
        out = scoring.parse_db_ts(datetime(2026, 1, 1))
        assert out.tzinfo == timezone.utc

    def test_invalid_string_returns_none(self):
        assert scoring.parse_db_ts("not-a-date") is None


# ── freshness ──

class TestFreshness:
    def test_no_date_is_fresh(self):
        assert scoring.freshness({}, _Cfg()) == 1.0

    def test_future_date_is_fresh(self):
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        assert scoring.freshness({"last_access_at": future}, _Cfg()) == 1.0

    def test_one_half_life_is_half(self):
        old = (datetime.now(timezone.utc) - timedelta(days=69)).isoformat()
        # half_life default 69 → 2^-1 = 0.5
        assert abs(scoring.freshness({"last_access_at": old}, _Cfg()) - 0.5) < 0.01

    def test_cfg_override_half_life(self):
        old = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        hl10 = scoring.freshness({"created_at": old}, _Cfg({"retrieval": {"decay_half_life": 10}}))
        hl100 = scoring.freshness({"created_at": old}, _Cfg({"retrieval": {"decay_half_life": 100}}))
        assert hl10 < hl100

    def test_last_access_preferred_over_created(self):
        recent = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        old = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
        got = scoring.freshness({"last_access_at": recent, "created_at": old}, _Cfg())
        assert got > 0.9


# ── gspo_cluster ──

class TestGspoCluster:
    def _m(self, source, sid, imp):
        return MemoryRecord(source=source, content="x", importance=imp,
                            metadata={"session_id": sid})

    def test_empty_session_ids_are_not_clustered(self):
        a = self._m("knowledge", "", 0.2)
        b = self._m("knowledge", "", 0.9)
        scoring.gspo_cluster([a, b])
        assert (a.importance, b.importance) == (0.2, 0.9)

    def test_singleton_not_clustered(self):
        a = self._m("knowledge", "s1", 0.3)
        scoring.gspo_cluster([a])
        assert a.importance == 0.3

    def test_low_variance_cluster_untouched(self):
        a = self._m("knowledge", "s1", 0.50)
        b = self._m("knowledge", "s1", 0.51)
        scoring.gspo_cluster([a, b])
        assert (a.importance, b.importance) == (0.50, 0.51)

    def test_high_variance_cluster_flattened_to_geometric_mean(self):
        a = self._m("knowledge", "s1", 0.2)
        b = self._m("knowledge", "s1", 0.8)
        scoring.gspo_cluster([a, b])
        assert a.importance == b.importance
        assert abs(a.importance - 0.4) < 1e-9  # sqrt(0.2*0.8)


# ── diversify_top_k ──

class TestDiversifyTopK:
    def _m(self, source, domain, imp):
        return MemoryRecord(source=source, content="x", importance=imp,
                            metadata={"domain": domain})

    def test_empty(self):
        assert scoring.diversify_top_k([]) == []

    def test_no_domain_items_pass_through(self):
        items = [self._m("s", "", 0.9), self._m("s", "", 0.8)]
        assert scoring.diversify_top_k(items, 5) == items

    def test_one_representative_per_domain_then_fill(self):
        items = [
            self._m("s", "ai", 0.9),
            self._m("s", "ai", 0.85),
            self._m("s", "db", 0.8),
            self._m("s", "ai", 0.7),
        ]
        out = scoring.diversify_top_k(items, 3)
        domains = [o.metadata["domain"] for o in out]
        assert "ai" in domains and "db" in domains
        assert len(out) == 3

    def test_respects_top_k(self):
        items = [self._m("s", f"d{i}", 0.9 - i * 0.01) for i in range(10)]
        assert len(scoring.diversify_top_k(items, 4)) == 4

    def test_nested_metadata_domain(self):
        m = MemoryRecord(source="s", content="x", importance=0.5,
                         metadata={"metadata": {"domain": "net"}})
        out = scoring.diversify_top_k([m], 1)
        assert out == [m]


# ── lang_novelty ──

class TestAddCoreGrams:
    def test_empty_noop(self):
        b = set()
        lang_novelty.add_core_grams(b, "")
        assert b == set()

    def test_cjk_produces_grams(self):
        b = set()
        lang_novelty.add_core_grams(b, "知识进化检测")
        assert len(b) > 0
        assert all(3 <= len(g) <= 4 for g in b)

    def test_ascii_only_dropped(self):
        b = set()
        lang_novelty.add_core_grams(b, "hello")
        assert b == set()


class TestCoreTermNovelty:
    def test_empty_text_zero(self):
        assert lang_novelty.core_term_novelty("", {"a"}) == 0.0

    def test_empty_corpus_half(self):
        assert lang_novelty.core_term_novelty("知识进化", set()) == 0.5

    def test_all_known_zero(self):
        known = set()
        lang_novelty.add_core_grams(known, "知识进化检测")
        assert lang_novelty.core_term_novelty("知识进化检测", known) == 0.0

    def test_all_new_one(self):
        known = set()
        lang_novelty.add_core_grams(known, "旧知识")
        assert lang_novelty.core_term_novelty("全新概念", known) == 1.0


class TestJaccardSimilarity:
    def test_identical_is_one(self):
        assert lang_novelty.jaccard_similarity("hello world", "hello world") == 1.0

    def test_empty_is_zero(self):
        assert lang_novelty.jaccard_similarity("", "hello") == 0.0

    def test_disjoint_is_zero(self):
        assert lang_novelty.jaccard_similarity("alpha beta", "gamma delta") == 0.0

    def test_partial_overlap_between_zero_and_one(self):
        sim = lang_novelty.jaccard_similarity(
            "websocket protocol framed messages",
            "websocket protocol framed messages reliable")
        assert 0.0 < sim < 1.0


class TestClassifyRelation:
    def test_replaces_at_high_sim(self):
        assert lang_novelty.classify_relation(0.95) == "replaces"

    def test_enriches_mid_sim(self):
        assert lang_novelty.classify_relation(0.75) == "enriches"

    def test_none_low_sim(self):
        assert lang_novelty.classify_relation(0.5) is None

    def test_boundaries(self):
        assert lang_novelty.classify_relation(0.9) == "replaces"
        assert lang_novelty.classify_relation(0.7) == "enriches"
