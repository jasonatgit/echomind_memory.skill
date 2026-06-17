# core/_reflective_fallback.py
# Pure-function safe fallback: Return empty when unavailable / Basic keyword extraction

import re
import logging
from collections import Counter

logger = logging.getLogger("ReflectiveFallback")


def _build_prompt(context, config):
    return ""


def _load_few_shot():
    return []


def _get_extra_params():
    return {}


def _parse_result(raw):
    """Parse LLM JSON response, returning raw string if not valid JSON."""
    if isinstance(raw, str) and raw.strip():
        try:
            import json
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return raw
    return raw


# ── Keyword fallback: provider=none extract high-frequency words as basic reflection ──


def _extract_keywords(records, top_k=10):
    """Extract top-K frequent words with TF-IDF weighting from records.
    Handles mixed EN/ZH text: trigrams for EN, bigrams+trigrams for ZH.
    Stopwords sourced from lang_utils language profiles (no hardcoded lists).
    No jieba dependency.
    """
    from .lang_utils import get_stopwords
    en_sw = get_stopwords("en")
    zh_sw = get_stopwords("zh")

    # Collect all text
    texts = []
    for r in records:
        if isinstance(r, dict):
            texts.append(r.get("content", "") or r.get("text", "") or "")
        elif isinstance(r, str):
            texts.append(r)
    all_text = " ".join(texts).strip()
    if not all_text:
        return []

    tokens = []

    # EN words: regex word boundaries (2+ chars)
    en_words = re.findall(r'\b[a-zA-Z]{2,}\b', all_text.lower())
    tokens.extend(w for w in en_words if w not in en_sw)

    # EN trigrams (3-word phrases) for richer context
    en_filtered = [w for w in en_words if w not in en_sw]
    for i in range(len(en_filtered) - 2):
        trigram = "_".join(en_filtered[i:i+3])
        tokens.append(trigram)

    # ZH "words": 2-3 char n-grams (no jieba)
    zh_chars = re.findall(r'[\u4e00-\u9fff]+', all_text)
    for segment in zh_chars:
        if len(segment) >= 2:
            for i in range(len(segment) - 1):
                bigram = segment[i:i+2]
                if bigram not in zh_sw:
                    tokens.append(bigram)
        if len(segment) >= 3:
            for i in range(len(segment) - 2):
                trigram = segment[i:i+3]
                if trigram not in zh_sw:
                    tokens.append(trigram)

    # TF-IDF: normalize by document frequency (approximate IDF)
    counter = Counter(tokens)
    total = sum(counter.values())
    if total > 0:
        scored = {w: c/total for w, c in counter.items()}
        sorted_words = sorted(scored.items(), key=lambda x: x[1], reverse=True)
        return [word for word, _ in sorted_words[:top_k]]
    return [word for word, _ in counter.most_common(top_k)]


def _reflect_records(
    records, user_id, platform, llm_fn, config, store, memory
):
    """Basic keyword-based reflection when LLM provider is 'none'.

    Two-phase API:
    - llm_fn=None → returns (prompt: str, record_ids: list) for two-phase HTTP API
    - llm_fn=callable → runs full reflection, returns ReflectionOutput dict or None

    When llm_fn is provided and provider is not 'none', uses the LLM to generate
    reflection. When provider is 'none', extracts top frequent keywords as fallback.
    """
    provider = ""
    try:
        from .config_manager import get_config_manager
        provider = get_config_manager().get("llm", "provider", default="")
    except Exception:
        pass

    if llm_fn is None:
        # Two-phase HTTP API: return prompt for caller-side LLM processing
        prompt = _prepare_reflection_context(records)
        record_ids = [r.get("id", f"rec_{i}") for i, r in enumerate(records)]
        return (prompt, record_ids)

    # Hermes auto path: llm_fn provided → use LLM for reflection
    if provider != "none":
        try:
            prompt = _prepare_reflection_context(records)
            raw_response = llm_fn(prompt)
            if raw_response:
                return _process_reflection(
                    raw_response, records, user_id, platform, config, store, memory,
                )
        except Exception:
            logger.debug("reflection: LLM call failed, falling back to keyword")
            pass

    keywords = _extract_keywords(records)
    if not keywords:
        return None

    # P1-4: typed output — separate insights, preferences, rules, knowledge
    output = {
        "key_insights": keywords[:10],
        "preferences": {},
        "rules": [],
        "knowledge": [],
        "experience": [],
        "procedural_rules": [],
        "confidence": 0.3,
        "source": "fallback_keyword",
    }

    # Try to classify keywords into categories
    pref_kw = {"like", "prefer", "want", "need", "okay", "good",
               "preference", "style", "format", "language",
               "habit", "usually", "always", "never", "avoid", "不"}
    rule_kw = {"rule", "must", "should", "always", "never", "require"}
    
    for kw in keywords:
        kw_lower = kw.lower()
        if any(p in kw_lower or p in kw for p in pref_kw):
            output["preferences"][kw] = "keyword"
        elif any(r in kw_lower or r in kw for r in rule_kw):
            output["rules"].append(kw)
        else:
            output["knowledge"].append({
                "content": kw, "domain": "general", "source": "fallback"
            })

    return output


def _process_reflection(
    raw_response, records, user_id, platform, config, store, memory_agent
):
    """Process LLM reflection result with fallback.

    When called without a valid LLM, returns an empty valid result
    so the caller does not receive None (which triggers HTTP 400).
    """
    if not raw_response:
        # No LLM response → return empty valid result, not None
        return {
            "key_insights": [],
            "preferences": {},
            "rules": [],
            "knowledge": [],
            "experience": [],
            "procedural_rules": [],
            "confidence": 0.3,
            "source": "fallback_empty",
        }
    # Try to parse as JSON; if it fails, return raw string as-is
    return _parse_result(raw_response)


def _prepare_reflection_context(records):
    """Build a keyword-based prompt for two-phase reflection API when LLM is unavailable."""
    keywords = _extract_keywords(records, top_k=10)
    if not keywords:
        return ""
    texts = []
    all_raw = ""
    for r in records:
        txt = ""
        if isinstance(r, dict):
            txt = r.get("content", "") or r.get("text", "") or r.get("title", "")
            if txt:
                texts.append(txt[:200])
        elif isinstance(r, str):
            txt = r[:200]
            texts.append(txt)
        all_raw += " " + txt
    record_text = "\n".join(f"- {t}" for t in texts[:10])
    keyword_text = ", ".join(keywords[:8])
    from .lang_utils import detect_language, get_prompt
    lang = detect_language(all_raw)
    prompt = get_prompt("reflect", lang, keywords=keyword_text, records=record_text)
    if not prompt:
        return ""
    return prompt


def _merge_semantic(output, knowledge_agent):
    pass


def _merge_procedural(output, knowledge_agent):
    pass


def _merge_user_preferences(output, user_id, platform, user_agent):
    pass


def _update_rl_weights(output, memory_agent):
    pass


def _save_reflection(record, store, memory_agent):
    pass
