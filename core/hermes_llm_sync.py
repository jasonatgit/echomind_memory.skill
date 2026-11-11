# EchoMind — Hermes config → EchoMind llm overrides
#
# Pure translation helper (no pydantic/fastapi imports) so the mapping can be
# unit-tested without the host. Reads the Hermes v0.23.1 schema:
#
#   model:
#     default: <model id>          # canonical key (was ignored until v1.2.20)
#     base_url: <url | ${ENV}>
#     provider: <name | custom:name>
#   providers:
#     <name>: {api|base_url, api_key, model}
#
# EchoMind's LLMClient speaks OpenAI-compatible chat-completions only, so the
# helper refuses providers it cannot talk to instead of posting an incompatible
# payload.

import logging

logger = logging.getLogger("HermesLLMSync")

# Provider values that (at least by default) resolve to an OpenAI-compatible
# endpoint. ``auto`` is accepted because Hermes resolves it per host; the URL
# is still the operator's explicit base_url.
_COMPATIBLE_PROVIDERS = frozenset({
    "", "auto", "openai", "openai_compatible", "openai-compatible",
    "custom", "local", "vllm", "ollama", "lmstudio", "deepseek",
})

# Providers whose native API is NOT OpenAI-compatible chat-completions.
# EchoMind cannot talk to these, so refuse rather than post an incompatible
# payload. Named OpenAI-compatible gateways that aren't enumerated above are
# still accepted when they carry an explicit endpoint (see the gate below).
_NON_OPENAI_PROVIDERS = frozenset({
    "anthropic", "claude", "google", "gemini", "bedrock", "vertex", "cohere",
})


def _expand(value) -> str:
    """Expand a whole-value ${VAR} reference; non-strings yield ''."""
    if not isinstance(value, str):
        return ""
    try:
        from .config_manager import expand_env_value
        value = expand_env_value(value, "")
    except Exception:
        pass
    return str(value or "").strip()


def parse_hermes_llm_config(hermes_conf: dict):
    """Translate a parsed Hermes config.yaml into EchoMind runtime overrides.

    Returns ``(overrides, provider_label)`` or ``None`` when there is no model
    section or the provider is not OpenAI-compatible. ``overrides`` keys use
    the same dotted ``llm.*`` form ``ConfigManager.set_runtime`` expects.
    """
    if not isinstance(hermes_conf, dict):
        return None
    model_cfg = hermes_conf.get("model")
    if not isinstance(model_cfg, dict) or not model_cfg:
        return None

    provider = str(model_cfg.get("provider") or "").strip()
    p_norm = provider.casefold()
    p_base = p_norm.split(":", 1)[0]
    is_custom = p_norm.startswith("custom:")

    # Provider-scoped block: providers.<name> with name = the part after
    # "custom:" (Hermes' own config uses e.g. provider: custom:ustc).
    provider_cfg = {}
    providers = hermes_conf.get("providers")
    if isinstance(providers, dict):
        names = []
        if is_custom:
            names.append(provider.split(":", 1)[1])
        if provider:
            names.append(provider)
        for name in names:
            cand = providers.get(name)
            if isinstance(cand, dict):
                provider_cfg = cand
                break

    endpoint = (model_cfg.get("endpoint")
                or model_cfg.get("base_url")
                or provider_cfg.get("api")
                or provider_cfg.get("base_url")
                or provider_cfg.get("endpoint")
                or "")
    has_endpoint = bool(str(endpoint or "").strip())

    # Compatibility gate: reject known non-OpenAI providers outright, then
    # accept a custom:<name> gateway or any provider that ships an explicit
    # endpoint (named gateways we don't enumerate — openrouter/groq/together/…
    # — are OpenAI-compatible in practice). Without an endpoint only the
    # allowlist is trusted.
    if p_base in _NON_OPENAI_PROVIDERS and not is_custom:
        return None
    if not is_custom and not has_endpoint and p_norm not in _COMPATIBLE_PROVIDERS:
        return None

    # Canonical model key is `default`; `model`/`default_model` are legacy
    # spellings kept for older hosts and hand-written configs.
    model_name = (model_cfg.get("default")
                  or model_cfg.get("model")
                  or model_cfg.get("default_model")
                  or provider_cfg.get("default")
                  or provider_cfg.get("model")
                  or "")
    api_key = model_cfg.get("api_key") or provider_cfg.get("api_key") or ""

    overrides = {"llm.provider": "openai_compatible"}
    endpoint = _expand(endpoint)
    api_key = _expand(api_key)
    model_name = str(model_name or "").strip()
    if endpoint:
        overrides["llm.endpoint"] = endpoint
    if api_key:
        overrides["llm.api_key"] = api_key
    if model_name:
        overrides["llm.model"] = model_name
    return overrides, provider
