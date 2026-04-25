import os

# Central model configuration for da-agent. Replace placeholders with your own
# endpoints/keys or override via environment variables.
default_http_base = "xxxxxx"
default_gemini_base = "https://<your-gemini-endpoint>/v1beta/openai/chat/completions"
default_anthropic_base = "https://api.your-anthropic-endpoint/v1/messages"
default_azure_base = "https://<your-azure-openai>.openai.azure.com"

model_config = {
    # General OpenAI-compatible chat endpoints (AUTH_TOKEN/API_URL)
    "gpt-4o-2024-11-20": {
        "provider": "http",
        "base_url_env": "API_URL",
        "base_url": default_http_base,
        "api_key_env": "AUTH_TOKEN",
    },
    "gpt-5-2025-08-07": {
        "provider": "http",
        "base_url_env": "API_URL",
        "base_url": default_http_base,
        "api_key_env": "AUTH_TOKEN",
    },
    "o3-2025-04-16": {
        "provider": "http",
        "base_url_env": "API_URL",
        "base_url": default_http_base,
        "api_key_env": "AUTH_TOKEN",
    },
    "gpt-oss-120b": {
        "provider": "http",
        "base_url_env": "API_URL",
        "base_url": default_http_base,
        "api_key_env": "AUTH_TOKEN",
    },
    "o4-mini-2025-04-16": {
        "provider": "http",
        "base_url_env": "API_URL",
        "base_url": default_http_base,
        "api_key_env": "AUTH_TOKEN",
    },
    "azure-grok-4": {
        "provider": "http",
        "base_url_env": "API_URL",
        "base_url": default_http_base,
        "api_key_env": "AUTH_TOKEN",
    },
    "glm-4.7": {
        "provider": "http",
        "base_url_env": "API_URL",
        "base_url": default_http_base,
        "api_key_env": "AUTH_TOKEN",
    },
    "openai_qwen3-235b-a22b": {
        "provider": "http",
        "base_url_env": "API_URL",
        "base_url": default_http_base,
        "api_key_env": "AUTH_TOKEN",
    },
    "openai_qwen3-30b-a3b": {
        "provider": "http",
        "base_url_env": "API_URL",
        "base_url": default_http_base,
        "api_key_env": "AUTH_TOKEN",
    },
    # Gemini example (OpenAI-compatible endpoint)
    "gemini-2.5-flash": {
        "provider": "http",
        "base_url_env": "GEMINI_API_URL",
        "base_url": default_gemini_base,
        "api_key_env": "GEMINI_API_KEY",
    },

    # Anthropic-compatible endpoint
    "gcp-claude4-sonnet": {
        "provider": "http",
        "base_url_env": "ANTHROPIC_API_URL",
        "base_url": default_anthropic_base,
        "api_key_env": "ANTHROPIC_AUTH_TOKEN",
    },

    # Ark-compatible endpoint
    "Ark-kimi-k2-250711": {
        "provider": "http",
        "base_url_env": "ARK_API_URL",
        "base_url": default_http_base,
        "api_key_env": "ARK_AUTH_TOKEN",
    },
    "Ark-deepseek-v3.1-0821": {
        "provider": "http",
        "base_url_env": "ARK_API_URL",
        "base_url": default_http_base,
        "api_key_env": "ARK_AUTH_TOKEN",
    },
    "Ark-deepseek-v3.2": {
        "provider": "http",
        "base_url_env": "ARK_API_URL",
        "base_url": default_http_base,
        "api_key_env": "ARK_AUTH_TOKEN",
    },
    "Doubao-Seed-1.6": {
        "provider": "http",
        "base_url_env": "ARK_API_URL",
        "base_url": default_http_base,
        "api_key_env": "ARK_AUTH_TOKEN",
    },
    "Ark-deepseek-v3.1-terminus": {
        "provider": "http",
        "base_url_env": "ARK_API_URL",
        "base_url": default_http_base,
        "api_key_env": "ARK_AUTH_TOKEN",
    },
    "Doubao-Seed-1.6-thinking": {
        "provider": "http",
        "base_url_env": "ARK_API_URL",
        "base_url": default_http_base,
        "api_key_env": "ARK_AUTH_TOKEN",
    },

    # Azure OpenAI example
    "gpt-5-codex-2025-09-15": {
        "provider": "azure",
        "base_url_env": "AZURE_OPENAI_BASE_URL",
        "base_url": default_azure_base,
        "api_key_env": "AZURE_OPENAI_API_KEY",
        "api_version": "2024-03-01-preview",
        "model_name": "gpt-5-codex-2025-09-15",
        "max_tokens": 1000,
    },
}


def resolve_model_config(model_name: str) -> dict:
    cfg = model_config.get(model_name)
    if not cfg:
        raise ValueError(f"Model config not found for {model_name}")
    resolved = dict(cfg)
    if resolved.get("psm_ignore_env"):
        return resolved
    base_url_env = cfg.get("base_url_env")
    api_key_env = cfg.get("api_key_env")
    psm_name_env = cfg.get("psm_name_env")
    psm_address_family_env = cfg.get("psm_address_family_env")
    psm_host_env = cfg.get("psm_host_env")
    psm_port_env = cfg.get("psm_port_env")
    if base_url_env:
        resolved["base_url"] = os.environ.get(base_url_env, cfg.get("base_url"))
    if api_key_env:
        resolved["api_key"] = os.environ.get(api_key_env, cfg.get("api_key"))
    if psm_name_env:
        resolved["psm_name"] = os.environ.get(psm_name_env, cfg.get("psm_name"))
    if psm_address_family_env:
        resolved["psm_address_family"] = os.environ.get(
            psm_address_family_env, cfg.get("psm_address_family")
        )
    if psm_host_env:
        resolved["psm_host"] = os.environ.get(psm_host_env, cfg.get("psm_host"))
    if psm_port_env:
        resolved["psm_port"] = os.environ.get(psm_port_env, cfg.get("psm_port"))
    if not resolved.get("psm_name"):
        resolved["psm_name"] = os.environ.get("OPENAI_PSM_NAME", resolved.get("psm_name"))
    if not resolved.get("psm_address_family"):
        resolved["psm_address_family"] = os.environ.get("OPENAI_PSM_AF", resolved.get("psm_address_family"))
    if not resolved.get("psm_host"):
        resolved["psm_host"] = os.environ.get("OPENAI_PSM_HOST", resolved.get("psm_host"))
    if not resolved.get("psm_port"):
        resolved["psm_port"] = os.environ.get("OPENAI_PSM_PORT", resolved.get("psm_port"))
    return resolved
