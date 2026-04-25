import os

# Example model configuration map for the public release. Replace the placeholder
# URLs, model names, and API keys with your own endpoints before running.
model_config = {
    "gemini-2.5-flash": {
        "model_name": "gemini-2.5-flash",
        "base_url": "xxxx",
        "api_key": "",
        "api_version": "2024-08-01-preview",
        "generate_kwargs": {"max_tokens": 16384, "temperature": 0},
    },
}

VISION_CAPABLE_MODEL_CONFIGS = {
    "gemini-2.5-flash",
}
