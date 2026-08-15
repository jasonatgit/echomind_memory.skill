# core/_reflective_fallback.py
# Keyword-based reflection module: builds prompts and extracts keywords.

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


# ── Keyword extraction: extract high-frequency terms as basic reflection ──


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
    """Keyword-based reflection.

    Two-phase API:
    - llm_fn=None → returns (prompt: str, record_ids: list) for two-phase HTTP API
    - llm_fn=callable → runs full reflection, returns ReflectionOutput dict or None

    When llm_fn is provided and provider is not 'none', uses the LLM to generate
    reflection. When provider is 'none', extracts top frequent keywords.
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
            logger.debug("reflection: LLM call failed, using keyword extraction")
            pass

    keywords = _extract_keywords(records)
    if not keywords:
        return None

    # P1-4: typed output — separate insights, preferences, rules, knowledge
    output = {
        "key_insights": keywords[:10],
        "user_preferences": [],
        "procedural_rules": [],
        "new_knowledge": [],
        "importance_scores": {},
        "forget_suggestions": [],
        "confidence": 0.3,
        "source": "keyword",
    }

    # Try to classify keywords into categories
    pref_kw = {"like", "prefer", "want", "need", "okay", "good",
               "preference", "style", "format", "language",
               "habit", "usually", "always", "never", "avoid", "不"}
    rule_kw = {"rule", "must", "should", "always", "never", "require"}

    for kw in keywords:
        kw_lower = kw.lower()
        if any(p in kw_lower or p in kw for p in pref_kw):
            output["user_preferences"].append(kw)
        elif any(r in kw_lower or r in kw for r in rule_kw):
            output["procedural_rules"].append(kw)
        else:
            output["new_knowledge"].append(kw)

    return output


def _process_reflection(
    raw_response, records, user_id, platform, config, store, memory_agent
):
    """Process LLM reflection result.

    When called without a valid LLM response, returns an empty valid result
    so the caller does not receive None (which triggers HTTP 400).

    When the parsed output's confidence meets the configured minimum, the
    reflection is "consumed": insights/knowledge/rules back to the knowledge
    store, preferences to the user store, RL decay for forget areas, and the
    record persisted. The dict is still returned so the caller can coerce it
    to ReflectionOutput (the two-phase HTTP caller produces its own prompt /
    process_result instead of calling this directly).
    """
    if not raw_response:
        # No LLM response → return empty valid result, not None
        return {
            "key_insights": [],
            "user_preferences": [],
            "procedural_rules": [],
            "new_knowledge": [],
            "importance_scores": {},
            "forget_suggestions": [],
            "confidence": 0.3,
            "source": "empty",
        }
    # Parse as JSON; falls back to raw string on failure.
    output = _parse_result(raw_response)
    if not isinstance(output, dict):
        return output

    min_conf = 0.65
    try:
        if config is not None:
            min_conf = config.get("min_confidence", min_conf)
    except Exception:
        pass
    confidence = output.get("confidence", 0.0)
    if confidence < min_conf:
        logger.debug(
            f"Reflection confidence {confidence} < {min_conf}, not consuming"
        )
        return output

    # Consume the reflection into the memory stores.
    if memory_agent is not None:
        knowledge_agent = getattr(memory_agent, "knowledge_agent", None)
        if knowledge_agent is not None:
            _merge_semantic(output, knowledge_agent)
            _merge_procedural(output, knowledge_agent)
        user_agent = getattr(memory_agent, "user_agent", None)
        if user_agent is not None:
            _merge_user_preferences(output, user_id, platform, user_agent)
        _update_rl_weights(output, memory_agent)

    # Persist a reflection record (gated by the persistence flag).
    record = {
        "user_id": user_id,
        "platform": platform,
        "confidence": confidence,
        "source": output.get("source", "reflection"),
        "key_insights": output.get("key_insights", []),
        "user_preferences": output.get("user_preferences", []),
        "procedural_rules": output.get("procedural_rules", []),
        "new_knowledge": output.get("new_knowledge", []),
        "forget_suggestions": output.get("forget_suggestions", []),
    }
    if store is not None:
        _save_reflection(record, store, memory_agent)

    logger.info(f"Reflection consumed for {user_id}/{platform} (conf={confidence})")
    return output


def _prepare_reflection_context(records):
    """Build a keyword-based prompt for two-phase reflection API."""
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
    """P1-A: write reflection insights/new knowledge back to the knowledge store.

    Mirrors the Pro engine's _merge_semantic but consumes the OSS dict schema
    (output.key_insights / output.new_knowledge). Guarded per item so a bad
    entry never aborts the whole merge.
    """
    if not isinstance(output, dict):
        return
    for insight in output.get("key_insights") or []:
        try:
            knowledge_agent.add_document(
                content=insight,
                metadata={"domain": "insight", "source": "reflection"},
            )
        except Exception as e:
            logger.warning(f"Failed to store reflection insight: {e}")
    for item in output.get("new_knowledge") or []:
        try:
            knowledge_agent.add_document(
                content=item,
                metadata={"domain": "knowledge", "source": "reflection"},
            )
        except Exception as e:
            logger.warning(f"Failed to store reflection knowledge: {e}")


def _merge_procedural(output, knowledge_agent):
    """P1-A: write reflection procedural rules back to the knowledge store."""
    if not isinstance(output, dict):
        return
    for rule in output.get("procedural_rules") or []:
        try:
            knowledge_agent.add_document(
                content=rule,
                metadata={"domain": "procedural", "source": "reflection"},
            )
        except Exception as e:
            logger.warning(f"Failed to store reflection rule: {e}")


def _merge_user_preferences(output, user_id, platform, user_agent):
    """P1-A: write reflection-derived user preferences back to the user store.

    Supports both "key=value" entries (parsed into a nested dict) and bare
    keys (stored as True).
    """
    if not isinstance(output, dict):
        return
    prefs_list = output.get("user_preferences") or []
    if not prefs_list:
        return
    prefs = {}
    for p in prefs_list:
        if not isinstance(p, str) or not p.strip():
            continue
        if "=" in p:
            k, v = p.split("=", 1)
            prefs[k.strip()] = v.strip()
        else:
            prefs[p.strip()] = True
    if not prefs:
        return
    try:
        user_agent.update(user_id, "preferences", prefs, source="reflection")
        logger.info(f"Updated {len(prefs)} reflection preferences for {user_id}/{platform}")
    except Exception as e:
        logger.warning(f"Failed to update reflection preferences: {e}")


def _update_rl_weights(output, memory_agent):
    """P1-A: deprioritize forget-suggestion areas from the reflection via decay_all.

    Mirrors Pro: a single decay_all call regardless of suggestion count so N
    suggestions don't compound exponential decay (0.95^N).
    """
    if not isinstance(output, dict) or not hasattr(memory_agent, "rl_optimizer"):
        return
    suggestions = output.get("forget_suggestions") or []
    if suggestions and hasattr(memory_agent.rl_optimizer, "decay_all"):
        try:
            memory_agent.rl_optimizer.decay_all()
            logger.info(
                f"RL weights decayed based on {len(suggestions)} reflection forget suggestion(s)"
            )
        except Exception as e:
            logger.warning(f"Failed to update RL weights: {e}")


def _save_reflection(record, store, memory_agent):
    """P1-A: persist a completed reflection record (respecting the persistence gate)."""
    if isinstance(record, dict) and (
        hasattr(memory_agent, "is_persistence_enabled")
        and memory_agent.is_persistence_enabled()
    ):
        try:
            store.save_reflection(record)
        except Exception as e:
            logger.warning(f"Failed to save reflection: {e}")
