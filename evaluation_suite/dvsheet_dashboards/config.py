import os

# Example model configuration map. Replace URLs/model names/API keys as needed.
model_config = {
    "gemini-2.5-flash": {
        "model_name": "gemini-2.5-flash",
        "base_url": "https://search.bytedance.net/gpt/openapi/online/multimodal/crawl",
        "api_key": os.getenv("DVSHEET_API_KEY", "qYfyWpYZO0y7T8GaojQcCQOxFNy1uayJ_GPT_AK"),
        "api_version": "2024-08-01-preview",
        "generate_kwargs": {"max_tokens": 26384, "temperature": 0},
    },
}

VISION_CAPABLE_MODEL_CONFIGS = {
    "gemini-2.5-flash",
}

