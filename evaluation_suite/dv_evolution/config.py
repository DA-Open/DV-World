import os

model_config = {
    "gemini-2.5-flash": {
        "model_name": "gemini-2.5-flash",
        "base_url": "xxxx",
        "api_key": os.getenv("DV_EVOL_API_KEY", ""),
        "api_version": "2024-08-01-preview",
        "generate_kwargs": {"max_tokens": 18096, "temperature": 0},
    },
    "gemini-2.5-pro": {
        "model_name": "gemini-2.5-pro",
        "base_url": "xxxx",
        "api_key": os.getenv("DV_EVOL_API_KEY", ""),
        "api_version": "2024-08-01-preview",
        "generate_kwargs": {"max_tokens": 18535, "temperature": 0},
    },
    "gemini-3-flash-preview": {
        "model_name": "gemini-3-flash-preview",
        "base_url": "xxxx",
        "api_key": os.getenv("DV_EVOL_API_KEY", ""),
        "api_version": "2024-08-01-preview",
        "generate_kwargs": {
            "max_tokens": 18096,
            "temperature": 0,
        },
    },
    "gpt-4.1-2025-04-14": {
        "provider": "bytedance",
        "model_name": "gpt-4.1-2025-04-14",
        "base_url": "xxxx",
        "api_key": os.getenv("DV_EVOL_API_KEY", ""),
        "api_version": "2024-08-01-preview",
        "generate_kwargs": {
            "max_tokens": 18096,
            "temperature": 0,
        },
    },
    "gpt-4o-2024-11-20": {
        "provider": "bytedance",
        "model_name": "gpt-4o-2024-11-20",
        "base_url": "xxxx",
        "api_key": os.getenv("DV_EVOL_API_KEY", ""),
        "api_version": "2024-08-01-preview",
        "generate_kwargs": {
            "max_tokens": 16384,
            "temperature": 0,
        },
    },

    

}

VISION_CAPABLE_MODEL_CONFIGS = set(model_config.keys())
