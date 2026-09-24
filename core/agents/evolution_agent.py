"""Knowledge evolution detection agent (v1.2.18 refactor, P2).

Extracted from MainMemoryAgent. Owns:
  - the known-core-term corpus cache (tenant/domain keyed)
  - the Jaccard + LLM relation detection that writes knowledge_evolution rows

MainMemoryAgent holds one instance (`self.evolution_agent`) and delegates its
`_detect_knowledge_evolution` / `_known_core_terms` / `_invalidate_core_term_cache`
/ `_llm_classify_relation` methods here, so call sites are unchanged.
"""

import logging
from typing import Callable, Dict, Optional

from ..lang_novelty import (
    add_core_grams, classify_relation, core_term_novelty, jaccard_similarity,
)

logger = logging.getLogger("MemoryAgent")


class KnowledgeEvolutionAgent:
    """Detects replaces/enriches/confirms/challenges relations between new
    knowledge and the existing corpus, and writes the evolution edges."""

    NOVELTY_THRESHOLD = 0.85
    MIN_TERM_STORE_SIZE = 20
    TERM_LIMIT = 500

    def __init__(self, db, knowledge_agent, cfg, llm_getter: Callable,
                 persistence_enabled_fn: Callable, *,
                 novelty_threshold: float = None,
                 min_term_store_size: int = None,
                 term_limit: int = None):
        self.db = db
        self.knowledge_agent = knowledge_agent
        self.cfg = cfg
        self._get_llm_client = llm_getter
        self._persistence_enabled = persistence_enabled_fn
        if novelty_threshold is not None:
            self.NOVELTY_THRESHOLD = novelty_threshold
        if min_term_store_size is not None:
            self.MIN_TERM_STORE_SIZE = min_term_store_size
        if term_limit is not None:
            self.TERM_LIMIT = term_limit
        # Known-term corpus cache: {(user_id, domain, limit) -> set[str]}
        self.cache: Dict[tuple, set] = {}

    # ── known-core-term corpus ──

    def known_core_terms(self, user_id: str, domain: str = "",
                         limit: int = None) -> set:
        """Build the "known core terms" set. In-memory store first; DB fallback
        when the in-memory store is below MIN_TERM_STORE_SIZE (cold start /
        eviction), fixing AEIS's `query_nodes(limit=80)` incompleteness with an
        exact SQL query instead of sampling.
        """
        limit = limit or self.TERM_LIMIT
        cache_key = (user_id, domain or "*", limit)
        if cache_key in self.cache:
            return self.cache[cache_key]

        known: set = set()
        entries = list(self.knowledge_agent.store.values())
        if domain:
            entries = [e for e in entries
                       if (e.metadata.get("domain") or e.metadata.get("category") or "") == domain]
        entries = entries[:limit]

        # DB fallback only when in-memory corpus is too thin (cold start/eviction)
        if len(entries) < self.MIN_TERM_STORE_SIZE and self._persistence_enabled():
            try:
                for content in self.db.get_knowledge_content(user_id, domain, limit):
                    add_core_grams(known, content)
            except Exception:
                logger.debug("Known-core-terms DB fallback failed; using memory only",
                             exc_info=True)

        for e in entries:
            add_core_grams(known, e.content)

        self.cache[cache_key] = known
        return known

    def invalidate_cache(self, user_id: str = None):
        """Drop cached known-term sets after a knowledge write/evict."""
        if not self.cache:
            return
        if user_id is None:
            self.cache.clear()
        else:
            self.cache = {
                k: v for k, v in self.cache.items() if k[0] != user_id
            }

    # ── relation classification ──

    def llm_classify_relation(self, source_text: str, target_text: str,
                              sim: float) -> Optional[str]:
        """Use LLM to precisely classify relation (replaces/enriches/confirms/challenges)."""
        try:
            llm = self._get_llm_client() if callable(self._get_llm_client) else None
            if not llm or not llm.available:
                return classify_relation(sim)
            prompt = (
                "Compare these two knowledge statements. Reply with ONE word:\n"
                "- 'replaces' if statement B makes statement A obsolete\n"
                "- 'enriches' if B adds useful detail to A\n"
                "- 'confirms' if B independently validates A\n"
                "- 'challenges' if B contradicts A\n"
                "- 'none' if unrelated\n\n"
                f"A: {source_text[:300]}\n\nB: {target_text[:300]}\n\n"
                "Relation:"
            )
            result = llm.chat(prompt, temperature=0, max_tokens=10).strip().lower()
            valid = {"replaces", "enriches", "confirms", "challenges"}
            return result if result in valid else classify_relation(sim)
        except Exception:
            return classify_relation(sim)

    # ── main entry ──

    def detect(self, content: str, user_id: str, domain: str = "general",
               knowledge_id: str = "", origin_agent: str = "",
               origin_session_id: str = "", origin_turn: int = 0):
        """Scan existing knowledge via Jaccard, classify relations, write evolution records.

        origin_* fields are recorded on the evolution rows (provenance, migration v9)
        so the relationship can be traced to the agent/session/turn that produced it.
        """
        if not self._persistence_enabled() or not content or len(content) < 20 or not knowledge_id:
            return
        try:
            candidates = self.knowledge_agent.search(query=content, user_id=user_id,
                                                     domain=domain, top_k=50)
            best_sim, best_id, best_content = 0.0, None, ""
            for c in candidates:
                # F3 (v1.2.15 audit): the freshly saved entry itself is always
                # in the candidate set with Jaccard 1.0, so the old post-loop
                # self-reference check (`best_id == knowledge_id`) made
                # evolution detection a deterministic no-op. Exclude it inside
                # the loop instead.
                c_id = c.get("id")
                if c_id == knowledge_id:
                    continue
                sim = jaccard_similarity(content[:500], (c.get("content", "") or "")[:500])
                if sim > best_sim:
                    best_sim, best_id, best_content = sim, c_id, c.get("content", "")
            # P-*: Core-term novelty gate — a sentence that mostly overlaps an old
            # one but carries a brand-new concept (high novelty) must not be
            # downgraded to replaces/enriches by the plain sentence-level Jaccard.
            # Low novelty (well-known) keeps the existing replace/enrich path.
            novelty = core_term_novelty(content, self.known_core_terms(user_id, domain))
            if best_sim > 0.7 and best_id and novelty < self.NOVELTY_THRESHOLD:
                relation = self.llm_classify_relation(best_content or "", content, best_sim)
                if relation:
                    self.db.save_evolution(best_id, knowledge_id, relation,
                        confidence=best_sim, reason="jaccard_match",
                        detection_method="llm" if best_sim < 0.9 else "jaccard",
                        origin_agent=origin_agent, origin_session_id=origin_session_id,
                        origin_turn=origin_turn)
                    if relation == "replaces" and best_sim >= 0.9:
                        self.db.save_memory_state("knowledge", best_id, "superseded",
                            reason=f"replaced_by:{knowledge_id}", source="evolution")
        except Exception as e:
            logger.debug("Knowledge evolution detection skipped: %s", e)
