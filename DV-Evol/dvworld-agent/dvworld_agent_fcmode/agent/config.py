import os

# Central model configuration for da-agent. Replace placeholders with your own
# endpoints/keys or override via environment variables.
default_http_base = "https://search.bytedance.net/gpt/openapi/online/v2/crawl/openai/deployments/gpt_openapi"
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
    "gemini-2.5-pro": {
        "provider": "bytedance",
        "model_name": "gemini-2.5-pro",
        "base_url": "https://search.bytedance.net/gpt/openapi/online/v2/crawl",
        "api_key": os.getenv("AUTH_TOKEN"),
        "generate_kwargs": {
            "max_tokens": 65535,
            "temperature": 0,
        },
    },
    "glm-4.6v": {
        "provider": "http",
        "base_url_env": "API_URL",
        "base_url": default_http_base,
        "api_key_env": "AUTH_TOKEN",
    },
    "openai_qwen3-coder-plus": {
        "provider": "bytedance",
        "model_name": "openai_qwen3-coder-plus",
        "base_url": "https://search.bytedance.net/gpt/openapi/online/v2/crawl",
        "api_key": os.getenv("AUTH_TOKEN"),
        "generate_kwargs": {
            "max_tokens": 65535,
            "temperature": 0,
        },
    },
    "openai_qwen3-vl-plus": {
        "provider": "http",
        "base_url_env": "API_URL",
        "base_url": default_http_base,
        "api_key_env": "AUTH_TOKEN",
    },
    "openai_qwen3-vl-235b-a22b-instruct": {
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
    "openai_qwen3-vl-235b-a22b-instruct": {
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
    "openai_qwen3-vl-32b-instruct": {
        "provider": "http",
        "base_url_env": "API_URL",
        "base_url": default_http_base,
        "api_key_env": "AUTH_TOKEN",
    },
    "gpt-5.1-2025-11-13": {
        "provider": "bytedance",
        "model_name": "gpt-5.1-2025-11-13",
        "base_url": "https://search.bytedance.net/gpt/openapi/online/v2/crawl",
        "api_key": os.getenv("AUTH_TOKEN"),
        "generate_kwargs": {
            "max_tokens": 65535,
            "temperature": 0,
        },
    },
    "gpt-4.1-2025-04-14": {
        "provider": "bytedance",
        "model_name": "gpt-4.1-2025-04-14",
        "base_url": "https://search.bytedance.net/gpt/openapi/online/v2/crawl",
        "api_key": os.getenv("AUTH_TOKEN"),
        "generate_kwargs": {
            "max_tokens": 65535,
            "temperature": 0,
        },
    },
    "gpt-5.2-2025-12-11": {
        "provider": "bytedance",
        "model_name": "gpt-5.2-2025-12-11",
        "base_url": "https://search.bytedance.net/gpt/openapi/online/v2/crawl",
        "api_key": os.getenv("AUTH_TOKEN"),
        "generate_kwargs": {
            "max_tokens": 65535,
            "temperature": 0,
        },
    },
    "kimi-k2-thinking": {
        "provider": "bytedance",
        "model_name": "kimi-k2-thinking",
        "base_url": "https://search.bytedance.net/gpt/openapi/online/v2/crawl",
        "api_key": os.getenv("AUTH_TOKEN"),
        "generate_kwargs": {
            "max_tokens": 65535,
            "temperature": 0,
        },
    },
    "qwen3-coder-30b-a3b-api": {
        "provider": "bytedance",
        "model_name": "openai_qwen3-coder-30b-a3b-instruct",
        "base_url": "https://search.bytedance.net/gpt/openapi/online/v2/crawl",
        "api_key": os.getenv("AUTH_TOKEN"),
        "generate_kwargs": {
            "max_tokens": 65535,
            "temperature": 0,
        },
    },
    "gemini-3-pro-preview-new": {
        "provider": "bytedance",
        "model_name": "gemini-3-pro-preview-new",
        "base_url": "https://search.bytedance.net/gpt/openapi/online/v2/crawl",
        "api_key": os.getenv("AUTH_TOKEN"),
        "generate_kwargs": {
            "max_tokens": 65535,
            "temperature": 0,
        },
    },
    "gemini-3-flash-preview": {
        "provider": "bytedance",
        "model_name": "gemini-3-flash-preview",
        "base_url": "https://search.bytedance.net/gpt/openapi/online/v2/crawl",
        "api_key": os.getenv("AUTH_TOKEN"),
        "generate_kwargs": {
            "max_tokens": 65535,
            "temperature": 0,
        },
    },
    "qwen3-coder-30b-a3b": {
        "provider": "psm",
        "psm_name": "inf.unified_server_qwen_tc.qwen3coder_2.service.hl",
        "psm_address_family": "v6",
        "psm_host": "",
        "psm_port": "",
        "api_path": "/v1",
        "model_name": "model",
        "bypass_proxy": True,
        "api_key": "mock-key",
        "psm_use_tools": True,
        "psm_ignore_env": True,
        "max_tokens": 8192,
    },
    "serve_dacomp_da_top_trajectories_doubao1221_test2_step_1330": {
        "provider": "psm",
        "psm_name": "inf.ray.serve_dacomp_da_top_trajectories_doubao1221_test2_step_1330.service.hl",
        "psm_address_family": "v6",
        "psm_host": "",
        "psm_port": "",
        "api_path": "/v1",
        "model_name": "model",
        "bypass_proxy": True,
        "api_key": "mock-key",
        "psm_use_tools": True,
        "psm_ignore_env": True,
        "max_tokens": 8192,
    },
    "serve_dacomp_da_gemini3_pro_4356_qwen_test1_step_408": {
        "provider": "psm",
        "psm_name_env": "QWEN3_PSM",
        "psm_name": "inf.ray.serve_dacomp_da_gemini3_pro_4356_qwen_test1_step_408_test1.service.hl",
        "psm_address_family": "v6",
        "psm_address_family_env": "QWEN3_PSM_AF",
        "psm_host_env": "QWEN3_HOST",
        "psm_port_env": "QWEN3_PORT",
        "psm_host": "",
        "psm_port": "",
        "api_path": "/v1/chat/completions",
        "model_name": "model",
        "bypass_proxy": True,
        "api_key_env": "AUTH_TOKEN",
    },
    "serve_dacomp_da_gemini3_pro_4356_qwen_test2": {
        "provider": "psm",
        "psm_name_env": "QWEN3_PSM",
        "psm_name": "inf.ray.serve_dacomp_da_gemini3_pro_4356_qwen_test2/step_1360.service.hl",
        "psm_address_family": "v6",
        "psm_address_family_env": "QWEN3_PSM_AF",
        "psm_host_env": "QWEN3_HOST",
        "psm_port_env": "QWEN3_PORT",
        "psm_host": "",
        "psm_port": "",
        "api_path": "/v1/chat/completions",
        "model_name": "model",
        "bypass_proxy": True,
        "api_key_env": "AUTH_TOKEN",
    },
    "serve_dacomp_da_gemini3_pro_4356_doubao_test2": {
        "provider": "psm",
        "psm_name_env": "QWEN3_PSM",
        "psm_name": "inf.seed_arena_evaluation.c90g0awhgc68c94451_k2i8da5iyy68c94456_unified_server.service.hl",
        "psm_address_family": "v6",
        "psm_address_family_env": "QWEN3_PSM_AF",
        "psm_host_env": "QWEN3_HOST",
        "psm_port_env": "QWEN3_PORT",
        "psm_host": "",
        "psm_port": "",
        "api_path": "/v1/chat/completions",
        "model_name": "model",
        "bypass_proxy": True,
        "api_key_env": "AUTH_TOKEN",
    },
    "doubao-seed-1-6-thinking-dataagent-preview": {
        "provider": "bytedance",
        "model_name": "doubao-seed-1-6-thinking-dataagent-preview",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
        "api_key": os.getenv("ARK_API_KEY"),
        "generate_kwargs": {
            "max_tokens": 65535,
            "temperature": 0,
        },
    },
    "doubao-seed-1-8-251215": {
        "provider": "bytedance",
        "model_name": "doubao-seed-1-8-251215",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
        "api_key": os.getenv("ARK_API_KEY"),
        "generate_kwargs": {
            "max_tokens": 65535,
            "temperature": 0,
        },
    },
    "deep-analyze": {
        "provider": "http",
        "base_url_env": "API_URL",
        "base_url": "http://[fdbd:dc02:c:653::14]:11019/v1/chat/completions",
        "model_name": "model",
    },
    "openai_qwen3-8b": {
        "provider": "http",
        "base_url_env": "API_URL",
        "base_url": default_http_base,
        "api_key_env": "AUTH_TOKEN",
    },
    "openai_qwen3-4b": {
        "provider": "http",
        "base_url_env": "API_URL",
        "base_url": default_http_base,
        "api_key_env": "AUTH_TOKEN",
    },
    "kimi-k2-0905-preview": {
        "provider": "http",
        "base_url_env": "API_URL",
        "base_url": default_http_base,
        "api_key_env": "AUTH_TOKEN",
    },
    "kimi-k2-thinking": {
        # Use the Bytedance gateway; keep key in AUTH_TOKEN
        "provider": "bytedance",
        "model_name": "kimi-k2-thinking",
        "base_url": "https://search.bytedance.net/gpt/openapi/online/v2/crawl",
        "api_key": os.getenv("AUTH_TOKEN"),
        "generate_kwargs": {
            "max_tokens": 65535,
            "temperature": 0,
        },
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
    "Doubao-Seed-1.6": {
        "provider": "http",
        "base_url_env": "ARK_API_URL",
        "base_url": default_http_base,
        "api_key_env": "ARK_AUTH_TOKEN",
    },
    "Doubao-Seed-1.8": {
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
