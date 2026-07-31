# core/lang_utils.py — Language-agnostic dispatcher
# All language-specific behavior is driven by language_profiles config.
# Adding a new language = adding a YAML section, zero code changes.

import re
import logging
from typing import List, Set, Optional, Dict, Any

logger = logging.getLogger(__name__)


_profiles_cache: Optional[dict] = None
_config_callable: Any = None


def _get_lang_profiles() -> dict:
    global _profiles_cache, _config_callable
    if _profiles_cache is not None:
        return _profiles_cache
    if _config_callable is None:
        from .config_manager import get_config_manager
        _config_callable = get_config_manager
    _profiles_cache = _config_callable().get_section("language_profiles")
    return _profiles_cache


def reload_lang_profiles():
    global _profiles_cache, _config_callable
    _profiles_cache = None
    _config_callable = None


def detect_language(text: str) -> str:
    if not text:
        return "en"
    profiles = _get_lang_profiles()
    detection_rules = profiles.get("detection", [])
    if not detection_rules:
        return "en"
    for rule in detection_rules:
        pattern = rule.get("pattern", "")
        threshold = rule.get("threshold", 0.3)
        if pattern:
            chars = re.findall(pattern, text)
            if len(chars) / max(len(text), 1) >= threshold:
                return rule["lang"]
    return "en"


def tokenize(text: str, lang: Optional[str] = None) -> List[str]:
    if lang is None:
        lang = detect_language(text)
    profile = _get_lang_profiles().get(lang, _get_lang_profiles().get("en", {}))
    strategy = profile.get("tokenizer", "word_boundary")
    if strategy == "char_ngram":
        return _char_ngram_tokenize(text, profile)
    elif strategy == "word_boundary":
        pattern = profile.get("tokenizer_pattern", r"[a-zA-Z]{2,}")
        return re.findall(pattern, text.lower())
    return text.lower().split()


def _char_ngram_tokenize(text: str, profile: dict) -> List[str]:
    min_n = profile.get("tokenizer_ngram_min", 2)
    max_n = profile.get("tokenizer_ngram_max", 3)
    char_pattern = profile.get("tokenizer_char_pattern",
                               r"[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]+")
    segments = re.findall(char_pattern, text)
    tokens = []
    for segment in segments:
        for n in range(min_n, max_n + 1):
            if len(segment) >= n:
                for i in range(len(segment) - n + 1):
                    tokens.append(segment[i:i + n])
    return tokens


def get_stopwords(lang: str) -> Set[str]:
    return set(_get_lang_profiles().get(lang, {}).get("stopwords", []))


def get_features(lang: str) -> Dict[str, List[str]]:
    return _get_lang_profiles().get(lang, {}).get("features", {})


def get_inference_keywords(lang: str) -> Dict[str, List[str]]:
    return _get_lang_profiles().get(lang, {}).get("inference", {})


def get_tool_descriptions(lang: str) -> Dict[str, str]:
    profiles = _get_lang_profiles()
    profile = profiles.get(lang, profiles.get("en", {}))
    td = profile.get("tool_descriptions", {})
    if not td:
        td = profiles.get("en", {}).get("tool_descriptions", {})
    return td


def get_prompt(name: str, lang: str, **fmt_kwargs) -> str:
    profiles = _get_lang_profiles()
    profile = profiles.get(lang, profiles.get("en", {}))
    template = profile.get("prompts", {}).get(name, "")
    if not template:
        template = profiles.get("en", {}).get("prompts", {}).get(name, "")
    if not template:
        return ""
    try:
        return template.strip().format(**fmt_kwargs)
    except KeyError as e:
        logger.warning("Prompt '%s' missing format key: %s", name, e)
        return ""