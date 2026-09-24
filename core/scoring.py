"""Pure scoring / ranking / freshness helpers for EchoMind retrieval.

Extracted from core/memory_agent.py (v1.2.18 refactor). These functions carry
no MainMemoryAgent state: constants and config are passed explicitly, so they
are independently testable (see tests/test_scoring.py) and safe to reuse.

MainMemoryAgent keeps thin same-named wrappers/delegates so all existing call
sites and subclass expectations are unchanged.
"""

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from typing import Protocol
except ImportError:  # pragma: no cover
    Protocol = object

from .models.memory_record import MemoryRecord


# ── Class constants moved from MainMemoryAgent (scoring-related) ──
# Kept as module defaults so callers can override via explicit arguments.
_DECAY_HALF_LIFE = 69  # days — freshness = 2^(-days / half_life)
_FRESHNESS_ARCHIVE_THRESHOLD = 0.1  # below this → archived


def score_base(terms, boosts=()) -> float:
    """P2.4: unified base score for RL-driven sources.

    terms: (value, weight) pairs of the signals this source carries.
    Normalizing by the sum of weights actually used keeps the base in
    [0,1] regardless of which dims a source provides, so every RL
    dimension is a real lever and no source is structurally shrunk by
    missing dims. boosts: multiplicative factors applied after
    normalization, capped at 1.0.
    """
    wsum = sum(w for _, w in terms)
    base = sum(v * w for v, w in terms) / wsum if wsum > 0 else 0.0
    for b in boosts:
        base *= b
    return min(1.0, base)


def parse_db_ts(value) -> Optional[datetime]:
    """Parse a DB timestamp value (string or datetime) into an aware UTC datetime.

    Handles both naive SQLite format ('YYYY-MM-DD HH:MM:SS') and aware ISO format.
    Returns None when value is empty/invalid so callers can fall back to defaults.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str) and value.strip():
        s = value.strip().replace(" ", "T")
        if "+" not in s and not s.endswith("Z") and not s.endswith("+00:00"):
            s += "+00:00"
        try:
            return datetime.fromisoformat(s)
        except ValueError:
            return None
    return None


def freshness(record: Dict[str, Any], cfg, half_life: float = _DECAY_HALF_LIFE) -> float:
    """Compute Ebbinghaus forgetting curve freshness.

    freshness = 2^(-days_since_last_access / half_life)
    Tries: last_access_at → created_at → last_updated.
    Returns 1.0 if no date available.
    """
    date_str = (
        record.get("last_access_at") or
        record.get("metadata", {}).get("last_access_at", "") or
        record.get("created_at") or
        record.get("metadata", {}).get("created_at", "") or
        record.get("last_updated") or
        record.get("metadata", {}).get("last_updated", "") or
        record.get("updated_at") or
        record.get("metadata", {}).get("updated_at", "") or
        ""
    )
    if not date_str or date_str == "":
        return 1.0
    dt = parse_db_ts(date_str)
    if dt is None:
        return 1.0
    # D3 fix: compute fractional days (seconds / 86400) instead of the
    # integer `.days` attribute. Records stored seconds/minutes ago were
    # previously all "0 days" → freshness pinned at 1.0, so the Ebbinghaus
    # decay did not begin until a full calendar day elapsed.
    days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
    if days < 0:
        return 1.0
    hl = half_life
    if cfg is not None:
        try:
            hl = cfg.get("retrieval", "decay_half_life", default=half_life)
        except Exception:
            hl = half_life
    return 2.0 ** (-days / max(float(hl), 0.01))


def gspo_cluster(scored: List[MemoryRecord]) -> List[MemoryRecord]:
    """GSPO-style cluster aggregation: same-source same-session memories
    share a geometric-mean importance score.

    Geometric mean = exp(mean(log(importance))) — more robust to outliers
    than arithmetic mean. Only active for clusters of size >= 2 where
    within-cluster variance exceeds threshold.
    """
    clusters = {}
    for mem in scored:
        sid = ""
        if isinstance(mem.metadata, dict):
            sid = mem.metadata.get("session_id", "") or mem.metadata.get("metadata", {}).get("session_id", "")
        if not sid:
            # F4b (v1.2.15 audit): an empty session_id merged every
            # same-source record into ONE cluster, flattening all their
            # individually-scored importances. No session scope → no
            # cluster.
            continue
        key = f"{mem.source}:{sid}"
        clusters.setdefault(key, []).append(mem)
    for key, members in clusters.items():
        if len(members) < 2:
            continue
        imps = [max(m.importance, 1e-8) for m in members]
        mean_imp = sum(imps) / len(imps)
        variance = sum((x - mean_imp) ** 2 for x in imps) / len(imps)
        cv = math.sqrt(variance) / max(mean_imp, 1e-8)
        if cv < 0.15:
            continue
        log_mean = sum(math.log(x) for x in imps) / len(imps)
        geo = math.exp(log_mean)
        for m in members:
            m.importance = geo
    return scored


def diversify_top_k(ranked: List[MemoryRecord], top_k: int = 8) -> List[MemoryRecord]:
    """Diversify top-K by domain grouping.

    P2.5: two-pass bucketed selection. Pass 1 guarantees one
    representative per domain present in the candidate pool (each
    domain's single highest-ranked item); pass 2 fills the remaining
    slots by global rank. The old single-pass form could let one dense
    domain occupy every slot (its later items only needed >= 80% of the
    last included item's importance), so the per-domain guarantee was
    unenforceable whenever a domain's top items dominated the pool.
    """
    if not ranked:
        return []

    def _item_domain(mem: MemoryRecord) -> str:
        if isinstance(mem.metadata, dict):
            # Direct domain key (experience, research, context)
            d = mem.metadata.get("domain", "") or mem.metadata.get("category", "") or ""
            if d:
                return d
            # Nested: knowledge_agent.search() puts whole result dict as metadata,
            # with domain/category inside mem.metadata["metadata"]
            inner = mem.metadata.get("metadata", {})
            if isinstance(inner, dict):
                return inner.get("domain", "") or inner.get("category", "") or ""
        return ""

    # Pass 1: one guaranteed representative per domain, in global rank order.
    domains_seen: set = set()
    result: List[MemoryRecord] = []
    deferred: List[MemoryRecord] = []
    for mem in ranked:
        domain = _item_domain(mem)
        if not domain or domain == "general":
            # items without domain always pass through
            result.append(mem)
        elif domain not in domains_seen:
            # First item of this domain — guaranteed spot
            domains_seen.add(domain)
            result.append(mem)
        else:
            deferred.append(mem)
        if len(result) >= top_k:
            break
    # Pass 2: fill remaining slots by global rank from the deferred items.
    for mem in deferred:
        if len(result) >= top_k:
            break
        result.append(mem)
    return result[:top_k]
