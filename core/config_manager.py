import copy
import os
import threading
import yaml
import logging
from typing import Any, Optional

logger = logging.getLogger("ConfigManager")


def _resolve_config_path(explicit_path: Optional[str] = None) -> str:
    if explicit_path:
        return os.path.expanduser(explicit_path)
    env_path = os.environ.get("ECHOMIND_CONFIG")
    if env_path:
        logger.info("Using config from ECHOMIND_CONFIG=%s", env_path)
        return os.path.expanduser(env_path)
    return os.path.expanduser("~/.echomind/echomind_config.yaml")


_SEARCH_PATHS = [
    "./echomind_config.yaml",
    "~/.echomind/echomind_config.yaml",
]


def _try_load_ext_params() -> dict:
    """Attempt to load supplementary engine parameters.

    Returns a dict of config overrides or empty dict.
    """

    try:
        from ._native_engine import _get_extra_params

        return _get_extra_params()
    except ImportError:
        return {}


def _load_bundled_keywords() -> dict:
    """Load domain keywords from the bundled domain_keywords.yaml.
    Returns empty dict on any failure — domain detection proceeds gracefully.
    """
    try:
        _here = os.path.dirname(os.path.abspath(__file__))
        _kw_path = os.path.join(_here, "..", "domain_keywords.yaml")
        with open(os.path.normpath(_kw_path), "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        logger.debug("Failed to load bundled domain keywords, using defaults")
    return {}


def _load_bundled_language_profiles() -> dict:
    """Load language profiles from the bundled language_profiles.yaml.
    This file is tracked in git and distributed to all users.
    Returns empty dict on any failure — language detection degrades gracefully.
    """
    try:
        _here = os.path.dirname(os.path.abspath(__file__))
        _lp_path = os.path.join(_here, "..", "language_profiles.yaml")
        with open(os.path.normpath(_lp_path), "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        logger.debug("Failed to load bundled language profiles, using defaults")
    return {}

FALLBACK_CONFIG = {
    "rl": {
        "initial_weights": {
            "relevance": [0.30, 0.50],
            "recency": [0.15, 0.25],
            "frequency": [0.10, 0.20],
            "explicit_feedback": [0.10, 0.20],
            "trust_score": [0.05, 0.15],
        },
        "learning_rate": 0.07,
        "decay_factor": 0.97,
        "max_buffer_size": 50,
        "seed": None,
    },
"reflection": {
        "batch_size": [5, 12],
        "max_daily":  [5, 20],
        "min_records": 6,
    },
    "retrieval": {
        "experience_top_k": 5,
        "experience_min_success_rate_initial": 0.7,
        "experience_min_success_rate_final": 0.6,
        "experience_limit": 5,
        "research_top_k": 5,
        "context_limit": 2,
        "preference_score_boost": 0.2,
        "relevance_multiplier": 0.6,
        "recency_multiplier": 0.5,
        "state_scan_limit": 1000,
    },
    "inference": {
        "min_occurrence": 2,
        "strategy": "keyword",
        "keywords": {
            "concise_response": ["brief", "concise"],
            "detailed_type": ["type hint", "Optional[str]"],
            "concise_code": ["concise", "no comments"],
        },
    },
    "topic_keywords": {},
    "llm": {
        "provider": "openai_compatible",
        "endpoint": "",
        "host": "",
        "port": 0,
        "api_key": "",
        "model": "local",
        "temperature": 0.3,
        "max_tokens": 1500,
        "timeout": 60,
        "semantic_model": "",
        "semantic_temperature": 0,
        "semantic_max_tokens": 4,
    },
    "server": {
        "host": "127.0.0.1",
        "port": 8005,
        "api_key": "",
        "cors_origins": ["http://localhost:8005"],
    },
    "domain": {
        "default": "general",
        "keywords": _load_bundled_keywords(),
    },
    "entities": {
        "technologies": [
            "python", "docker", "postgresql", "react", "node.js",
            "machine-learning", "microservices",
        ],
    },
    "language_profiles": _load_bundled_language_profiles(),
    "default_project": "default",
}


class ConfigManager:

    def __init__(
        self, config_path: Optional[str] = None, ext_params: Optional[dict] = None
    ):
        self._config_path = _resolve_config_path(config_path)
        self._ext_params = (
            ext_params if ext_params is not None else _try_load_ext_params()
        )
        self._search_paths = _SEARCH_PATHS.copy()
        self._search_paths.append(self._config_path)
        self._yaml_cache: dict = {}
        self._runtime_overrides: dict = {}
        self._active_path: Optional[str] = None
        self._observers: list = []
        self._load_config()

    def _load_config(self):
        for path_candidate in self._search_paths:
            full_path = os.path.expanduser(path_candidate)
            if not os.path.exists(full_path):
                continue
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                self._active_path = full_path
                self._yaml_cache = data or {}
                self._validate_config()
                logger.info("Config loaded from: %s", full_path)
                return
            except (yaml.YAMLError, OSError) as e:
                logger.warning(
                    "Config parse error (%s): %s, trying next path", full_path, e
                )
                continue
        logger.info("No valid config found, using FALLBACK_CONFIG")
        self._active_path = None
        self._yaml_cache = {}

    def _validate_config(self):
        """Lightweight schema validation for critical config values.

        Logs warnings for invalid values and reverts to FALLBACK_CONFIG defaults.
        Schema: {section.key: (expected_type, range_tuple, validator_fn)}
        """
        schema = {
            "server.port": (int, None, lambda v: v > 0 and v < 65536),
            "reflection.max_daily": (int, None, lambda v: v > 0),
            "reflection.batch_size": (int, None, lambda v: v > 0),
            "reflection.min_records": (int, None, lambda v: v > 0),
            "rl.learning_rate": (float, None, lambda v: 0 < v < 1),
            "rl.decay_factor": (float, None, lambda v: 0 < v < 1),
            "rl.max_buffer_size": (int, None, lambda v: v > 0),
        }
        for section_key, (expected_type, type_b, validator) in schema.items():
            sec, key = section_key.split(".", 1)
            sec_data = self._yaml_cache.get(sec, {})
            if not isinstance(sec_data, dict):
                continue
            val = sec_data.get(key)
            if val is None:
                continue
            # Type check
            if not isinstance(val, expected_type):
                # Allow list/tuple for random-range configs (reflection.batch_size etc.)
                if isinstance(val, (list, tuple)):
                    continue
                logger.warning(
                    "Config %s: expected %s, got %s (value=%r). Using default.",
                    section_key, expected_type.__name__, type(val).__name__, val,
                )
                del sec_data[key]
                continue
            # Range check
            if validator and not validator(val):
                logger.warning(
                    "Config %s: value %r out of valid range. Using default.",
                    section_key, val,
                )
                del sec_data[key]

    def get(self, section: str, key: str, default: Any = None) -> Any:
        runtime_key = f"{section}.{key}"
        if runtime_key in self._runtime_overrides:
            return self._runtime_overrides[runtime_key]

        # YAML takes priority over engine ext_params (user config wins)
        yaml_val = self._yaml_cache.get(section, {}).get(key)
        if yaml_val is not None:
            return yaml_val

        ext_val = self._ext_params.get(section, {}).get(key)
        if ext_val is not None:
            return ext_val

        section_fb = FALLBACK_CONFIG.get(section, {})
        if isinstance(section_fb, dict):
            return section_fb.get(key, default)

        return default

    def get_top_level(self, key: str, default: Any = None) -> Any:
        """Read a top-level (non-sectioned) config key, e.g. `default_project`.

        Top-level keys live alongside sections in the YAML, so they are not
        reachable via get(section, key). Precedence: runtime override (keyed as
        the bare key) > YAML top-level value > FALLBACK_CONFIG top-level value >
        default.
        """
        if key in self._runtime_overrides:
            return self._runtime_overrides[key]
        yaml_val = self._yaml_cache.get(key)
        if yaml_val is not None:
            return yaml_val
        fb_val = FALLBACK_CONFIG.get(key)
        if fb_val is not None:
            return fb_val
        return default

    def get_section(self, section: str) -> dict:
        base = copy.deepcopy(FALLBACK_CONFIG.get(section, {}))

        def _deep_update(target, source):
            for k, v in source.items():
                if isinstance(v, dict) and isinstance(target.get(k), dict):
                    target[k] = _deep_update(dict(target[k]), v)
                else:
                    target[k] = v
            return target

        # ext_params applied first (lowest priority), then YAML overwrites (user config wins)
        # Deep-copy to prevent callers from mutating cached values
        ext_sec = copy.deepcopy(self._ext_params.get(section, {}))
        if isinstance(ext_sec, dict):
            _deep_update(base, ext_sec)
        yaml_sec = copy.deepcopy(self._yaml_cache.get(section, {}))
        if isinstance(yaml_sec, dict):
            _deep_update(base, yaml_sec)
        # Apply runtime overrides (set via set_runtime)
        runtime = {}
        for kp, kv in self._runtime_overrides.items():
            parts = kp.split(".", 1)
            if len(parts) == 2 and parts[0] == section:
                runtime[parts[1]] = kv
        if runtime:
            _deep_update(base, runtime)
        return base

    def set_runtime(self, key_path: str, value: Any):
        self._runtime_overrides[key_path] = value
        logger.info("Runtime override: %s = %s", key_path, value)

    def on_reload(self, callback):
        """Register callback invoked on config reload."""
        self._observers.append(callback)

    def reload(self):
        # Preserve runtime overrides across reload (e.g. Hermes LLM sync)
        saved_overrides = dict(self._runtime_overrides)
        self._load_config()
        self._runtime_overrides.clear()
        self._runtime_overrides.update(saved_overrides)
        # Notify LLM client singleton to reload on next get (if any)
        try:
            from .llm_client import reload_llm_client
            reload_llm_client()
        except Exception:
            pass
        # Invalidate lang_utils profile cache
        try:
            from .lang_utils import reload_lang_profiles
            reload_lang_profiles()
        except Exception:
            pass
        for cb in self._observers:
            try:
                cb()
            except Exception as e:
                logger.warning("Config reload observer failed: %s", e)

    @property
    def config_path(self) -> str:
        return self._active_path or self._config_path


_config_manager: Optional[ConfigManager] = None
_config_manager_lock = threading.Lock()


def get_config_manager(
    config_path: Optional[str] = None, ext_params: Optional[dict] = None
) -> ConfigManager:
    global _config_manager
    if config_path is None and ext_params is None:
        if _config_manager is not None:
            return _config_manager
        with _config_manager_lock:
            if _config_manager is None:
                _config_manager = ConfigManager()
        return _config_manager
    return ConfigManager(config_path=config_path, ext_params=ext_params)
