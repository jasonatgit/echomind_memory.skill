"""Unit tests for the RL weight optimizer (M-8).

Runs against the pure-Python RLWeightOptimizer with no SQLite dependency.
Covers the invariants the audit flagged:
  - H-2: _update_weights and decay_all must keep weights sum-normalized
         (no two divergent "weight" semantics across code paths).
  - H-1: load_weights_for_user must reset to deterministic defaults when the
         user has no saved weights, not inherit the previous user's weights.
  - M-4: per-source RCW multipliers must not freeze a weight dimension at 0
         when no mapped source appears in the feedback's memories.
  - basic convergence: positive feedback raises weighting on mapped dims.
"""

import numpy as np
import pytest

from core.learning.rl_weight_optimizer import (
    RLWeightOptimizer,
    FeedbackRecord,
)


def _optimizer(**kw) -> RLWeightOptimizer:
    """Fresh optimizer with deterministic seed, full default weights."""
    kw.setdefault("seed", 0)
    kw.setdefault("max_buffer_size", 50)  # allow >1 update within a test
    return RLWeightOptimizer(initial_weights={}, **kw)


def _feedback(user_feedback, mems=None, **meta):
    return FeedbackRecord(
        user_id="u1",
        task_id="t1",
        retrieved_memories=mems or [],
        user_feedback=user_feedback,
        metadata=meta,
    )


# ── H-2: weight normalization invariants ────────────────────────────

def test_default_weights_sum_to_one():
    opt = _optimizer()
    assert abs(sum(opt.weights.values()) - 1.0) < 1e-6
    assert abs(sum(opt.ema_weights.values()) - 1.0) < 1e-6


def test_default_weights_are_deterministic():
    a = _optimizer(seed=1).weights
    b = _optimizer(seed=999).weights  # seed must NOT matter for defaults
    assert a == b


def test_update_weights_preserves_sum_invariant():
    opt = _optimizer()
    for _ in range(10):
        opt.add_feedback(_feedback("positive"))
    # add_feedback flushes every 10 records by default (min(10, max_buffer_size))
    assert abs(sum(opt.weights.values()) - 1.0) < 1e-4
    assert abs(sum(opt.ema_weights.values()) - 1.0) < 1e-4


def test_decay_all_preserves_sum_invariant_after_clamp():
    """decay_all must land on sum=1 (linear renormalize) even though each
    dimension is individually clamped to its _WEIGHT_SPEC range first."""
    opt = _optimizer()
    opt.snapshot_policy()
    # Force a plausible pre-decision snapshot for divergence computation
    opt.decay_all(factor=0.95)
    assert abs(sum(opt.weights.values()) - 1.0) < 1e-4


def test_decay_all_keeps_each_dimension_in_spec_range():
    opt = _optimizer()
    opt.snapshot_policy()
    opt.decay_all(factor=0.95)
    for k, spec in RLWeightOptimizer._WEIGHT_SPEC.items():
        lo, hi = spec["range"]
        assert lo <= opt.weights[k] <= hi, f"{k}={opt.weights[k]:.3f} outside {spec['range']}"


def test_decay_all_smooth_ema():
    """decay_all should advance the EMA toward the new weights (not reset it)."""
    opt = _optimizer()
    opt.snapshot_policy()
    before = opt.ema_weights["relevance"]
    opt.decay_all(factor=0.95)
    # EMA moves toward current weights by (1 - decay_factor)
    assert abs(opt.ema_weights["relevance"] - (0.98 * before + 0.02 * opt.weights["relevance"])) < 1e-6


# ── H-1: per-user isolation ─────────────────────────────────────────

def test_load_empty_user_resets_to_defaults():
    opt = _optimizer()
    # First user with explicit weights.
    custom = {"relevance": 0.5, "recency": 0.5, "frequency": 0.0,
              "explicit_feedback": 0.0, "trust_score": 0.0}
    opt.load_weights_for_user(custom)
    assert opt.weights["relevance"] == 0.5

    # Second user with NO saved weights must NOT inherit the first user's.
    opt.load_weights_for_user({})
    defaults = _optimizer().weights
    assert opt.weights == defaults


def test_load_empty_user_weights_sum_to_one():
    opt = _optimizer()
    opt.load_weights_for_user({})
    assert abs(sum(opt.weights.values()) - 1.0) < 1e-6


def test_load_weights_copies_not_shares():
    opt = _optimizer()
    custom = {"relevance": 0.4, "recency": 0.2, "frequency": 0.2,
              "explicit_feedback": 0.1, "trust_score": 0.1}
    opt.load_weights_for_user(custom)
    custom["relevance"] = 0.9  # mutate caller's dict afterwards
    assert opt.weights["relevance"] == 0.4  # optimizer holds its own copy


# ── M-4: RCW must not freeze a weight dimension ─────────────────────

def test_rcw_returns_nonzero_when_mapped_source_absent():
    """explicit_feedback maps to ['user'] only. If the feedback memories carry
    no 'user' source, the multiplier must fall back to 1.0 (neutral), never 0,
    which would otherwise zero out delta and freeze the dimension forever."""
    opt = _optimizer()
    mems = [{"source": "context", "relevance": 0.8}]  # no 'user' source
    rcw = opt._compute_rcw_advantages(_feedback("negative", mems))
    for k in RLWeightOptimizer._WEIGHT_KEYS:
        assert rcw[k] > 0, f"dimension {k} frozen at RCW=0"


def test_rcw_non_negative_always():
    opt = _optimizer()
    mems = [{"source": "user", "relevance": 0.9, "metadata": {"trust_score": 0.8}}]
    rcw = opt._compute_rcw_advantages(_feedback("positive", mems))
    for k in RLWeightOptimizer._WEIGHT_KEYS:
        assert rcw[k] >= 0


# ── convergence: repeated positive feedback drives learning ─────────

def test_positive_feedback_raises_mapped_dimensions():
    """After many positive feedbacks on knowledge-heavy retrievals, relevance
    (mapped from knowledge) should exceed its default, and the EMA should move."""
    opt = _optimizer()
    mems = [{"source": "knowledge", "relevance": 0.9,
             "metadata": {"trust_score": 0.9}}] * 4
    default_rel = opt.weights["relevance"]
    for _ in range(30):
        opt.add_feedback(_feedback("positive", mems[:]))
    assert opt.ema_weights["relevance"] > default_rel


def test_predict_score_range():
    """predict_score must return a finite, sane value for typical states."""
    opt = _optimizer()
    state = opt.extract_state({}, [{"source": "knowledge", "relevance": 0.5}] * 8)
    score = opt.predict_score(state)
    assert np.isfinite(score)


# ── P5-A: per-user learning meta-state isolation ───────────────────

def test_meta_state_isolated_per_user():
    """One user's feedback may advance only their own LR/exploration schedule,
    history and snapshots — never the other user's (process-wide) counter."""
    opt = _optimizer()
    # _feedback() stamps user_id="u1", so these 10 feedbacks drive user u1.
    for _ in range(10):
        opt.add_feedback(_feedback("positive"))
    # u1 did one full flush → 1 update; u2 (untouched) must be pristine.
    assert opt._meta_for("u1")["update_counter"] == 1
    assert len(opt._history_for("u1")) == 1
    assert opt._meta_for("u2")["update_counter"] == 0
    assert opt._meta_for("u2")["epsilon_step"] == 0
    assert opt._history_for("u2") == []
    assert opt._snapshots_for("u2") == []
    # u1's state is untouched while inspecting u2.
    assert opt._meta_for("u1")["update_counter"] == 1


def test_public_meta_attrs_follow_active_user():
    """The read-through scalars/lists (update_counter, history, ...) reflect
    whichever user's weights are currently loaded."""
    opt = _optimizer()
    for _ in range(10):
        opt.add_feedback(_feedback("positive"))  # user_id="u1"
    opt.load_weights_for_user({}, user_id="u2")
    assert opt.update_counter == 0  # pristine u2
    assert opt.history == []
    opt.load_weights_for_user({}, user_id="u1")
    assert opt.update_counter == 1  # u1's advanced counter
    assert len(opt.history) == 1
    # get_history is user-scoped too.
    assert opt.get_history(user_id="u2") == []
    assert len(opt.get_history(user_id="u1")) == 1