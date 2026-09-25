# EchoMind — Paired bootstrap gate for knowledge-update admission
#
# Recuris absorption #4 (validation-gated memory evolution): a knowledge
# rewrite/addition is admitted ONLY when paired held-out evidence supports it
# — a bootstrap CI over items (clusters), not single samples, excludes zero
# AND the regression count stays within reg_cap. Nothing here consults a
# model; arithmetic disposes.
#
# Design aligned with Recuris gates.held_out_paired_gate:
#   * bootstrap resamples ITEMS, not trials — samples within one item are
#     correlated, resampling them would report an interval far narrower than
#     the evidence supports;
#   * `material` floors what counts as an improvement/regression for dense
#     scores (0.97 vs 0.95 noise must not flip the regression counter);
#   * admission requires the CI low bound > 0 (not just net > 0), and the
#     "not significant" case is reported as such — abstention is a valid
#     outcome, not a rejection.

import random
import statistics
from typing import Any, Dict, Optional

# stdlib-only: no numpy dependency (the RL optimizer may not be installed in
# minimal deployments; this gate must always be importable).

DEFAULT_N_BOOT = 3000
DEFAULT_ALPHA = 0.05
DEFAULT_REG_CAP = 1
DEFAULT_SEED = 20260925


def held_out_paired_gate(base_items: Dict[str, float],
                         cand_items: Dict[str, float],
                         reg_cap: int = DEFAULT_REG_CAP,
                         n_boot: int = DEFAULT_N_BOOT,
                         alpha: float = DEFAULT_ALPHA,
                         material: float = 0.0,
                         seed: int = DEFAULT_SEED) -> Dict[str, Any]:
    """Paired bootstrap gate over held-out items.

    base_items / cand_items: item id -> score for the SAME items on both
    sides (e.g. per-entry historical hit rate before/after a knowledge
    rewrite). Items missing on either side are ignored (intersection).

    Returns {accept, net, ci:[lo,hi], n_improved, n_regressed, reason}:
    - accept is True iff the bootstrap CI low bound > 0 AND the regression
      count <= reg_cap;
    - an empty intersection reports insufficient (never a confident zero).
    """
    items = sorted(set(base_items) & set(cand_items))
    if not items:
        return {"accept": False, "net": 0.0, "ci": [0.0, 0.0],
                "n_improved": 0, "n_regressed": 0,
                "status": "insufficient",
                "reason": "no shared items between base and candidate"}

    # Per-item paired difference (each item is one cluster).
    diffs = [float(cand_items[i]) - float(base_items[i]) for i in items]
    net = statistics.mean(diffs)

    floor = max(material, 1e-9)
    n_up = sum(1 for d in diffs if d > floor)
    n_dn = sum(1 for d in diffs if d < -floor)

    # Bootstrap over items (NOT over the samples within an item).
    rng = random.Random(seed)
    n_boot = max(1, int(n_boot))
    boots = sorted(
        statistics.mean(diffs[rng.randrange(len(diffs))] for _ in diffs)
        for _ in range(n_boot)
    )
    lo = boots[min(int((alpha / 2) * n_boot), n_boot - 1)]
    hi = boots[min(int((1 - alpha / 2) * n_boot) - 1, n_boot - 1)]

    accept = (lo > 0) and (n_dn <= reg_cap)
    if accept:
        reason = "ci excludes zero and regressions within cap"
    elif n_dn > reg_cap:
        reason = f"regressions ({n_dn}) exceed reg_cap ({reg_cap})"
    else:
        reason = "CI includes zero — not significant (abstain, not reject)"

    return {
        "accept": accept,
        "net": round(net, 4),
        "ci": [round(lo, 4), round(hi, 4)],
        "n_improved": n_up,
        "n_regressed": n_dn,
        "n_items": len(items),
        "status": "decided" if (lo > 0 or n_dn > reg_cap) else "not_significant",
        "reason": reason,
    }
