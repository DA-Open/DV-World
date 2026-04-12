import json
import re
from pathlib import Path
from typing import List, Dict


def load_trajectory_text(path: Path, max_steps: int = 100, max_chars: int = 400000) -> str:
    """
    Load trajectory file and render a compact text summary with step numbers.
    Accepts content that is:
    - A JSON object with key "trajectory"
    - A bare JSON array
    - A text file containing `"trajectory": [ ... ]`
    """
    if not path or not path.exists():
        return "No trajectory provided."
    raw = path.read_text(encoding="utf-8")
    data = None
    try:
        data = json.loads(raw)
    except Exception:
        # try to extract array
        match = re.search(r"\[(.|\n)*\]", raw)
        if match:
            try:
                data = json.loads(match.group(0))
            except Exception:
                data = None
    if isinstance(data, dict) and "trajectory" in data:
        data = data.get("trajectory")
    if not isinstance(data, list):
        return raw[:max_chars]
    start = max(0, len(data) - max_steps)
    parts: List[str] = []
    for idx, step in enumerate(data[start:], start=start + 1):
        thought = step.get("thought", "") if isinstance(step, dict) else ""
        action = step.get("action", "") if isinstance(step, dict) else ""
        obs = step.get("observation", "") if isinstance(step, dict) else ""
        parts.append(f"Step {idx} Thought: {thought}\nAction: {action}\nObservation: {obs}")
    text = "\n---\n".join(parts)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n[truncated]"
    return text

