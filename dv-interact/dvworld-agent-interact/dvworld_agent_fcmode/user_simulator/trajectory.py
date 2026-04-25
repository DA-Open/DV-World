from typing import List, Dict


def summarize_trajectory(history: List[Dict[str, str]], max_turns: int = 5) -> str:
    """Summarize recent turns into a compact string."""
    if not history:
        return "No prior questions."
    recent = history[-max_turns:]
    parts = []
    for item in recent:
        q = item.get("agent", "") or ""
        a = item.get("response", "") or ""
        parts.append(f"Q: {q} | A: {a}")
    return " || ".join(parts)

