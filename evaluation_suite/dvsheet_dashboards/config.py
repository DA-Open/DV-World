import os

# Example model configuration map. Replace URLs/model names/API keys as needed.
model_config = {
    "gemini-2.5-flash": {
        "model_name": "gemini-2.5-flash",
        "base_url": "xxxx",
        "api_key": os.getenv("DVSHEET_API_KEY", ""),
        "api_version": "2024-08-01-preview",
        "generate_kwargs": {"max_tokens": 26384, "temperature": 0},
    },
}

VISION_CAPABLE_MODEL_CONFIGS = {
    "gemini-2.5-flash",
}

