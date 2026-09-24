"""Pure CJK/token novelty + Jaccard helpers.

Extracted from core/memory_agent.py (v1.2.18 refactor). No MainMemoryAgent
state — independently testable (see tests/test_scoring.py).

Note: `known_core_terms` (which needs db / knowledge_agent / cache) and
`llm_classify_relation` (which needs an LLM client) stay on MainMemoryAgent;
only the pure leaves live here.
"""

import re
from typing import Optional


def add_core_grams(bag: set, text: str):
    """Extract 3-4 char CJK core n-grams from *text* into *bag* (in place).

    Charset matches jaccard_similarity's CJK bigram convention (hanzi +
    kana + hangul). Pure digit/ASCII runs are dropped as noise (AEIS par).
    """
    if not text:
        return
    for seg in re.split(r'[^\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]+', text):
        cleaned = seg
        for n in (4, 3):
            for i in range(len(cleaned) - n + 1):
                g = cleaned[i:i + n]
                if g and not re.fullmatch(r'[\dA-Za-z_]+', g):
                    bag.add(g)


def core_term_novelty(text: str, known_corpus: set) -> float:
    """Novelty ratio of new core terms (new info fraction, not new sentence).

    Returns [0,1]: 1.0 = all core terms unseen, 0.0 = all seen. Special:
    empty/no-core-term text → 0.0; empty known corpus (cold start) → 0.5
    meaning "undetermined" rather than "half new" (aligned with AEIS).
    """
    if not text:
        return 0.0
    grams = set()
    add_core_grams(grams, text)
    if not grams:
        return 0.0
    if not known_corpus:
        return 0.5
    novel = sum(1 for g in grams if g not in known_corpus)
    return novel / len(grams)


def jaccard_similarity(text1: str, text2: str) -> float:
    """Jaccard similarity on tokens — fast, zero-LLM approx.

    P8 fix: the previous `text.lower().split()` was whitespace-based, so
    for CJK text (no spaces) it produced a single giant token per string
    and Jaccard≈0 — silently disabling knowledge-evolution detection for
    Chinese. Now tokenize via lang_utils (which handles EN words and ZH
    char n-grams) and, for CJK, additionally union in character bigrams
    so short overlapping phrases still score non-zero.
    """
    if not text1 or not text2:
        return 0.0
    from .lang_utils import tokenize as _tok, detect_language as _det

    def _tokens(t: str) -> set:
        lang = _det(t)
        toks = set(_tok(t, lang)) if t.strip() else set()
        # Audit (MED-8/R2): CJK bigrams must be added REGARDLESS of the
        # overall language detection. The previous guard `if lang == "zh"`
        # silently dropped all hanzi in a mixed zh/en string whose EN bytes
        # dominated (detect_language -> "en"), re-introducing the P8 bug it
        # was meant to fix; ja (kana) and ko (hangul) never got bigrams at
        # all. Extracting character bigrams from any CJK/kana/hangul
        # segment is a strict superset of the old behaviour — it only adds
        # tokens, never removes them. R2 additionally fixed by covering
        # \u3040-\u30ff (kana) and \uac00-\ud7af (hangul).
        segs = re.findall(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]+", t.lower())
        big = {s[i:i+2] for s in segs for i in range(len(s) - 1) if len(s) >= 2}
        toks |= big
        return toks

    set1 = _tokens(text1)
    set2 = _tokens(text2)
    inter = len(set1 & set2)
    union = len(set1 | set2)
    return inter / union if union > 0 else 0.0


def classify_relation(sim: float) -> Optional[str]:
    """Classify relation type from Jaccard similarity alone."""
    if sim >= 0.9:
        return "replaces"
    if sim >= 0.7:
        return "enriches"
    return None
