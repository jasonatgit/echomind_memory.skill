# core/_reflective_fallback.py
# Pure-function safe fallback: Return empty when unavailable / Basic keyword extraction

import re
from collections import Counter


def _build_prompt(context, config):
    return ""


def _load_few_shot():
    return []


def _get_extra_params():
    return []


def _get_pro_seeds():
    return {}


def _parse_result(raw):
    return raw


# ── Keyword fallback: provider=none extract high-frequency words as basic reflection ──

_STOPWORDS_EN = {
    "the", "is", "are", "a", "an", "and", "or", "but", "in", "on",
    "to", "for", "of", "with", "at", "from", "by", "that", "this",
    "it", "as", "be", "was", "has", "have", "had", "not", "no",
    "if", "so", "we", "you", "he", "she", "they", "i", "my", "me",
    "your", "his", "her", "our", "their", "can", "will", "just",
    "what", "when", "where", "which", "who", "how", "all", "also",
    "do", "does", "did", "been", "being", "would", "could", "should",
    "more", "some", "any", "only", "very", "about", "than", "then",
    "now", "other", "into", "its", "these", "those", "each", "every",
    "over", "much", "such", "after", "before", "between", "through",
    "during", "may", "might", "must", "shall", "need", "want", "know",
    "think", "thing", "well", "use", "see", "make", "get", "way",
    "take", "come", "give", "find", "tell", "ask", "try", "leave",
    "call", "keep", "let", "seem", "help", "show", "mean", "set",
    "put", "move", "work", "old", "long", "even", "back", "still",
    "here", "there", "up", "out", "new", "like", "good", "great",
    "right", "same", "while", "really", "again", "go", "first",
}

_STOPWORDS_ZH = {
    "", "了", "is", "我", "在", "有", "和", "就", "不", "人",
    "都", "一", "a", "上", "也", "很", "到", "说", "要", "去",
    "你", "会", "着", "no", "看", "好", "itself", "这", "他", "她",
    "它", "们", "那", "些", "what", "how", "how to", "can", "this",
    "that", "because", "therefore", "but", "although", "If", "or", "already",
    "maybe", "should", "must", "think", "know", "", "一种", "some",
    "not", "or", "here", "there", "this way", "that way", "when", "after",
    "before", "then", "now", "comparison", "need", "use", "issue", "work",
    "content", "perform", "system", "method", "passed", "implement", "Completed", "process",
    "situation", "relationship", "part", "result", "start", "end", "Handle", "manage",
    "support", "development", "test", "check", "confirm", "maintain", "maintenance", "Update",
    "related", "consider", "suggestion", "note", "indeed", "really", "very", "many",
}


def _extract_keywords(records, top_k=10):
    """Extract top-K frequent words with TF-IDF weighting from records.
    Handles mixed EN/ZH text: trigrams for EN (v1.1.0), bigrams for ZH.
    No jieba dependency.
    """
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
    tokens.extend(w for w in en_words if w not in _STOPWORDS_EN)

    # EN trigrams (3-word phrases) for richer context
    en_filtered = [w for w in en_words if w not in _STOPWORDS_EN]
    for i in range(len(en_filtered) - 2):
        trigram = "_".join(en_filtered[i:i+3])
        tokens.append(trigram)

    # ZH "words": 2-4 char bigrams (no jieba)
    zh_chars = re.findall(r'[\u4e00-\u9fff]+', all_text)
    for segment in zh_chars:
        if len(segment) >= 2:
            for i in range(len(segment) - 1):
                bigram = segment[i:i+2]
                if bigram not in _STOPWORDS_ZH:
                    tokens.append(bigram)
            # Also add 3-char trigrams for specificity
            if len(segment) >= 3:
                for i in range(len(segment) - 2):
                    trigram = segment[i:i+3]
                    if trigram not in _STOPWORDS_ZH:
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
    """Basic keyword-based reflection when the compiled extension is unavailable.

    Only activates when provider is explicitly 'none' (no LLM available).
    Extracts top frequent keywords as key_insights with low confidence.
    """
    provider = ""
    if isinstance(config, dict):
        provider = config.get("provider", "")
        if not provider:
            # Check nested llm config (from ConfigManager path)
            llm_cfg = config.get("llm", {})
            if isinstance(llm_cfg, dict):
                provider = llm_cfg.get("provider", "")

    if provider != "none":
        return None

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
    pref_kw = {"like", "prefer", "want", "need", "okay", "good", "like",
               "preference", "style", "format", "language", "language",
               "habit", "usually", "always", "never", "avoid", "不", "like",
               "preferences", "habits", "always", "never", "avoid"}
    rule_kw = {"rule", "must", "should", "always", "never", "require",
               "rule", "must", "require", "rule", "must", "should"}
    
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
    return None


def _prepare_reflection_context(records):
    return ""


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
