from __future__ import annotations

import base64
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any

from evaluation_suite.dv_interact.config import model_config
from evaluation_suite.dv_interact.prompt import JUDGE_PROMPT

logger = logging.getLogger(__name__)

@dataclass
class EvalResult:
    total_raw: float
    total_norm: float
    items: Dict[str, float]
    model_raw: str
    prompt_used: str
    dim_scores: Dict[str, float] | None = None
    dim_percents: Dict[str, float] | None = None


def _make_client(cfg):
    from openai import AzureOpenAI, OpenAI

    api_key = cfg["api_key"]
    base_url = cfg["base_url"]
    api_version = cfg.get("api_version")
    headers = cfg.get("headers") or {}

    if api_version:
        return AzureOpenAI(azure_endpoint=base_url, api_key=api_key, api_version=api_version, default_headers=headers)
    return OpenAI(base_url=base_url, api_key=api_key, default_headers=headers)


def _file_to_data_url(path: Path) -> str:
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _parse_scores(content: str, total_points: float) -> EvalResult:
    items: Dict[str, float] = {}
    dim_scores: Dict[str, float] = {}
    dim_percents: Dict[str, float] = {}
    total_raw = 0.0
    cleaned = content.strip()
    # Strip code fences if present
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.replace("json", "", 1).strip()
    try:
        data = json.loads(cleaned)
        # Expect nested dimensions with subtotals and Total_Score
        for dim_key, dim_val in data.items():
            if not isinstance(dim_val, dict):
                continue
            subtotal = dim_val.get("subtotal")
            if subtotal is not None:
                try:
                    total_raw += float(subtotal)
                    dim_scores[dim_key] = float(subtotal)
                except Exception:
                    pass
            # collect per-standard scores
            for std_key, std_val in dim_val.items():
                if not isinstance(std_val, dict):
                    continue
                sc = std_val.get("score")
                if sc is not None:
                    try:
                        items[f"{dim_key}:{std_key}"] = float(sc)
                    except Exception:
                        continue
        if "Total_Score" in data:
            try:
                total_raw = float(data.get("Total_Score", total_raw))
            except Exception:
                pass
    except Exception:
        pass
    total_norm = max(0.0, min(1.0, total_raw / total_points)) if total_points > 0 else 0.0
    return EvalResult(
        total_raw=total_raw,
        total_norm=total_norm,
        items=items,
        model_raw=content,
        prompt_used="",
        dim_scores=dim_scores,
        dim_percents=dim_percents or None,
    )


def evaluate_task(
    query_text: str,
    rubric_text: str,
    trajectory_text: str,
    chart_img: Path | None,
    model_name: str = "gemini-2.5-flash",
    total_points: float = 10.0,
    dim_max_scores: Dict[str, float] | None = None,
) -> EvalResult:

    if model_name not in model_config:
        raise ValueError(f"Model config '{model_name}' not found.")
    cfg = model_config[model_name]
    client = _make_client(cfg)

    prompt = JUDGE_PROMPT.format(
        user_query=query_text.strip(),
        rubric=rubric_text.strip(),
        trajectory=trajectory_text.strip(),
        total_points=total_points,
    )
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
            ],
        }
    ]
    if chart_img and Path(chart_img).exists():
        messages[0]["content"].append(
            {"type": "image_url", "image_url": {"url": _file_to_data_url(Path(chart_img))}}
        )

    max_retries = int(cfg.get("max_retries", 30))
    last_exc = None
    response = None
    for attempt in range(1, max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=cfg["model_name"],
                messages=messages,
                stream=False,
                **cfg.get("generate_kwargs", {}),
            )
            last_exc = None
            break
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "Judge call failed (model=%s, attempt=%d/%d): %s",
                cfg.get("model_name"),
                attempt,
                max_retries,
                exc,
            )
            time.sleep(0.2)
    if response is None and last_exc is not None:
        logger.error("Judge call failed after %d attempts (model=%s)", max_retries, cfg.get("model_name"))
        raise last_exc

    content = response.choices[0].message.content if response and response.choices else ""
    parsed = _parse_scores(content or "", total_points)
    # compute per-dimension percents if provided
    if dim_max_scores:
        perc = {}
        for k, v in (parsed.dim_scores or {}).items():
            # match exact key (e.g., "Dimension_1")
            max_v = dim_max_scores.get(k) if isinstance(dim_max_scores, dict) else None
            if max_v is None:
                continue
            try:
                max_v_f = float(max_v)
                if max_v_f > 0:
                    perc[k] = max(0.0, min(1.0, float(v) / max_v_f))
            except Exception:
                continue
        parsed.dim_percents = perc
    parsed.prompt_used = prompt
    return parsed
