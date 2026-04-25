"""
DVSheet-Dashboards evaluator (rubric + LLM judge).

This task type grades a dashboard Excel by exporting the whole dashboard to an image
and letting a multimodal model score it against a rubric.
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, List


@dataclass
class EvalResult:
    score: float
    score_percent: float
    vlm_total_raw: float
    vlm_total_norm: float
    vlm_dims_raw: Dict[str, float]
    vlm_dims_norm: Dict[str, float]
    vlm_max_scores: Dict[str, float]
    model_raw: str
    prompt_used: str
    debug: str


def _ensure_repo_on_path():
    import sys

    root = Path(__file__).resolve().parents[2]
    sys.path.append(str(root))


_ensure_repo_on_path()

from evaluation_suite.dvsheet_dashboards.config import model_config  # noqa: E402
from evaluation_suite.dvsheet_dashboards.prompt import RUBRIC_PROMPT  # noqa: E402


def dashboard_summary_text(extracted_context: Optional[str]) -> str:
    """
    Only include dashboard data (tables + per-chart series) in `{chart_data}`.
    Avoid adding non-data boilerplate like file names.
    """
    return (extracted_context or "").strip()


def _extract_json(content: str) -> Optional[dict]:
    # Try direct JSON first, then extract the first {...} block.
    try:
        return json.loads(content)
    except Exception:
        pass
    m = re.search(r"\{.*\}", content, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _normalize(value: float, min_v: float, max_v: float) -> float:
    if max_v <= min_v:
        return 0.0
    x = (value - min_v) / (max_v - min_v)
    return max(0.0, min(1.0, x))


def _parse_vlm_json(content: str, max_scores: Dict[str, float]) -> Dict[str, Any]:
    """
    Parse rubric JSON:
    - Read per-dimension subtotal (or sum of child scores)
    - Total_Score preferred; otherwise sum of subtotals
    - Normalize by metadata Total when available
    """
    dims_raw: Dict[str, float] = {}
    dims_norm: Dict[str, float] = {}
    total_raw: Optional[float] = None

    parsed = _extract_json(content or "")
    rubric_keys_order = [k for k in (max_scores or {}).keys() if k.lower() != "total"]

    if parsed and isinstance(parsed, dict):
        for dim_key, dim_val in parsed.items():
            if not isinstance(dim_val, dict):
                continue
            subtotal = dim_val.get("subtotal")
            if subtotal is None:
                subtotal_sum = 0.0
                for _, std_val in dim_val.items():
                    if not isinstance(std_val, dict):
                        continue
                    sc = std_val.get("score")
                    if sc is None:
                        continue
                    try:
                        subtotal_sum += float(sc)
                    except Exception:
                        continue
                subtotal = subtotal_sum
            if subtotal is not None:
                try:
                    dims_raw[dim_key] = float(subtotal)
                except Exception:
                    pass
        if "Total_Score" in parsed:
            try:
                total_raw = float(parsed.get("Total_Score", 0.0))
            except Exception:
                total_raw = 0.0
        elif dims_raw:
            total_raw = sum(dims_raw.values())

    if total_raw is None:
        def _parse_score_from_text(txt: str) -> float:
            try:
                m = re.search(r"Total_Score\"?\s*:\s*([0-9]+(?:\\.[0-9]+)?)", txt)
                if m:
                    return float(m.group(1))
            except Exception:
                pass
            return 0.0
        total_raw = _parse_score_from_text(content)

    total_points = max_scores.get("Total") if max_scores else None
    total_norm = max(0.0, min(1.0, total_raw / total_points)) if total_points and total_points > 0 else 0.0

    if max_scores:
        if dims_raw and all(k.lower().startswith("dimension") for k in dims_raw.keys()) and rubric_keys_order:
            remapped = {}
            for idx, dk in enumerate(sorted(dims_raw.keys())):
                if idx < len(rubric_keys_order):
                    remapped[rubric_keys_order[idx]] = dims_raw.get(dk, 0.0)
                else:
                    remapped[dk] = dims_raw.get(dk, 0.0)
            dims_raw = remapped
        for dk in max_scores:
            if dk.lower() == "total":
                continue
            dims_raw.setdefault(dk, 0.0)
        for dk, raw in dims_raw.items():
            max_v = max_scores.get(dk)
            if max_v:
                dims_norm[dk] = max(0.0, min(1.0, raw / max_v))

    return {
        "total_raw": float(total_raw or 0.0),
        "total_norm": float(total_norm),
        "dims_raw": dims_raw,
        "dims_norm": dims_norm,
        "max_scores": max_scores or {},
    }


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


def vlm_judge_mm(
    *,
    query_text: str,
    rubric_text: str,
    max_scores: Dict[str, float],
    dashboard_text: str,
    dashboard_imgs: List[Path],
    model_name: str,
) -> Dict[str, Any]:
    """
    Multimodal judge: text + image.
    """
    if model_name not in model_config:
        raise ValueError(f"Model config '{model_name}' not found.")
    cfg = model_config[model_name]
    client = _make_client(cfg)

    prompt = RUBRIC_PROMPT.format(
        user_query=query_text.strip(),
        rubric=rubric_text.strip(),
        chart_data=dashboard_text.strip(),
    )
    imgs = [p for p in (dashboard_imgs or []) if p is not None and Path(p).exists()]
    content_parts: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
    for p in imgs:
        content_parts.append({"type": "image_url", "image_url": {"url": _file_to_data_url(Path(p))}})
    messages = [{"role": "user", "content": content_parts}]

    response = None
    last_err = ""
    for _ in range(3):
        try:
            response = client.chat.completions.create(
                model=cfg["model_name"],
                messages=messages,
                stream=False,
                **cfg.get("generate_kwargs", {}),
            )
            break
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
            import time
            time.sleep(0.5)
    content = response.choices[0].message.content if response and response.choices else ""
    if not content and last_err:
        content = f"[error] {last_err}"
    parsed = _parse_vlm_json(content or "", max_scores)
    return {
        "total_raw": parsed["total_raw"],
        "total_norm": parsed["total_norm"],
        "dims_raw": parsed["dims_raw"],
        "dims_norm": parsed["dims_norm"],
        "raw": content,
        "prompt": prompt,
        "max_scores": parsed.get("max_scores", {}),
    }


def evaluate_dashboard(
    *,
    workbook_path: Optional[Path],
    dashboard_imgs: List[Path],
    extracted_context_text: Optional[str],
    query_text: str,
    rubric_text: str,
    max_scores: Dict[str, float],
    model_name: str,
) -> EvalResult:
    debug_lines = []
    dash_text = dashboard_summary_text(extracted_context_text)

    vlm_response: Dict[str, Any] = vlm_judge_mm(
        query_text=query_text,
        rubric_text=rubric_text,
        max_scores=max_scores,
        dashboard_text=dash_text,
        dashboard_imgs=dashboard_imgs,
        model_name=model_name,
    )

    score = float(vlm_response.get("total_norm", 0.0))
    debug_lines.append(f"vlm_total_raw={vlm_response.get('total_raw', 0.0)}")
    debug_lines.append(f"vlm_total_norm={vlm_response.get('total_norm', 0.0)}")

    return EvalResult(
        score=score,
        score_percent=score * 100.0,
        vlm_total_raw=float(vlm_response.get("total_raw", 0.0)),
        vlm_total_norm=float(vlm_response.get("total_norm", 0.0)),
        vlm_dims_raw=vlm_response.get("dims_raw", {}) or {},
        vlm_dims_norm=vlm_response.get("dims_norm", {}) or {},
        vlm_max_scores=vlm_response.get("max_scores", {}) or {},
        model_raw=str(vlm_response.get("raw", "")),
        prompt_used=str(vlm_response.get("prompt", "")),
        debug="\n".join(debug_lines),
    )


__all__ = ["EvalResult", "evaluate_dashboard", "vlm_judge_mm"]
