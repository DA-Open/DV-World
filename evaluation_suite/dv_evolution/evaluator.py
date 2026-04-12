from __future__ import annotations

import base64
import json
import logging
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any

import pandas as pd

from evaluation_suite.dv_evolution.config import model_config
from evaluation_suite.dv_evolution.prompt import VLM_VIS_PROMPT_ZH

logger = logging.getLogger(__name__)


@dataclass
class EvalResult:
    s_vis: float  # normalized to [0,1]
    s_table: float
    score: float
    debug: Dict[str, Any]
    model_raw: str = ""
    prompt_used: str = ""
    dims: Dict[str, Any] = None  # raw subtotals per dimension
    dims_norm: Dict[str, Any] = None  # normalized per dimension


def _file_to_data_url(path: Path) -> str:
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _make_client(cfg):
    from openai import AzureOpenAI, OpenAI

    api_key = cfg["api_key"]
    base_url = cfg["base_url"]
    api_version = cfg.get("api_version")
    headers = cfg.get("headers") or {}

    if api_version:
        return AzureOpenAI(azure_endpoint=base_url, api_key=api_key, api_version=api_version, default_headers=headers)
    return OpenAI(base_url=base_url, api_key=api_key, default_headers=headers)


def vlm_visual_score(
    *,
    gold_img: Path,
    cand_img: Path,
    model_name: str,
    task_context: str,
) -> EvalResult:
    if model_name not in model_config:
        raise ValueError(f"Model config '{model_name}' not found.")
    cfg = model_config[model_name]
    client = _make_client(cfg)

    prompt = VLM_VIS_PROMPT_ZH.format(task_context=task_context.strip())
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": _file_to_data_url(gold_img)}},
                {"type": "image_url", "image_url": {"url": _file_to_data_url(cand_img)}},
            ],
        }
    ]

    max_retries = int(cfg.get("max_retries", 100))
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
                "VLM call failed (model=%s, attempt=%d/%d): %s",
                cfg.get("model_name"),
                attempt,
                max_retries,
                exc,
            )
            time.sleep(0.2)
    if response is None and last_exc is not None:
        logger.error("VLM call failed after %d attempts (model=%s)", max_retries, cfg.get("model_name"))
        raise last_exc
    content = response.choices[0].message.content if response and response.choices else ""
    total_raw = 0.0
    dims: Dict[str, float] = {}

    def _extract_json_block(txt: str):
        cleaned = txt.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            cleaned = cleaned.replace("json", "", 1).strip()
        try:
            return json.loads(cleaned)
        except Exception:
            import re

            m = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(0))
                except Exception:
                    return None
        return None

    data = _extract_json_block(content or "")
    dim_max = {
        "Dimension_1": 4.0,  # Data Integrity: 4 items
        "Dimension_2": 6.0,  # Style Imitation: 6 items
        "Dimension_3": 6.0,  # Layout & Aesthetics: 6 items
    }
    if isinstance(data, dict):
        for dim_key, dim_val in data.items():
            if not isinstance(dim_val, dict):
                continue
            subtotal = dim_val.get("subtotal")
            if subtotal is None:
                # fallback: sum child scores
                subtotal_sum = 0.0
                for std_key, std_val in dim_val.items():
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
                    dims[dim_key] = float(subtotal)
                except Exception:
                    pass
        if "Total_Score" in data:
            try:
                total_raw = float(data.get("Total_Score", 0.0) or 0.0)
            except Exception:
                total_raw = 0.0
        else:
            total_raw = sum(dims.values()) if dims else 0.0
    else:
        # Regex fallbacks for malformed/partial JSON
        import re

        total_match = re.search(r"Total_Score\"?\s*:\s*([0-9]+(?:\.[0-9]+)?)", content)
        if total_match:
            try:
                total_raw = float(total_match.group(1))
            except Exception:
                total_raw = 0.0
        if not dims:
            subs = re.findall(r"subtotal\"?\s*:\s*([0-9]+(?:\.[0-9]+)?)", content)
            if subs:
                try:
                    dims["fallback_subtotals"] = sum(float(x) for x in subs)
                    if total_raw == 0.0:
                        total_raw = dims["fallback_subtotals"]
                except Exception:
                    pass

    dims_norm: Dict[str, float] = {}
    for k, v in dims.items():
        max_v = dim_max.get(k)
        if max_v:
            try:
                dims_norm[k] = max(0.0, min(1.0, float(v) / max_v))
            except Exception:
                continue
    total_norm = max(0.0, min(1.0, total_raw / 16.0))
    return EvalResult(
        s_vis=total_norm,
        s_table=0.0,
        score=total_norm,
        debug={"raw": content, "dims": dims, "total_raw": total_raw},
        model_raw=content,
        prompt_used=prompt,
        dims=dims,
        dims_norm=dims_norm,
    )


def _normalize_val(v):
    if pd.isna(v):
        return None
    try:
        f = float(v)
        if math.isfinite(f):
            return round(f, 2)
    except Exception:
        pass
    return str(v).strip()


def table_similarity(gold_csv: Path, cand_csv: Path, tol: float = 1e-6) -> float:
    if not gold_csv.exists() or not cand_csv.exists():
        return 0.0
    try:
        gdf = pd.read_csv(gold_csv)
        cdf = pd.read_csv(cand_csv)
    except Exception:
        return 0.0

    common_cols = [c for c in gdf.columns if c in cdf.columns]
    if not common_cols:
        return 0.0
    gdf = gdf[common_cols]
    cdf = cdf[common_cols]
    if len(gdf) == 0 or len(cdf) == 0:
        return 0.0

    # Normalize values and count frequency by column to ignore row order
    def col_counter(df):
        counters = {}
        for col in df.columns:
            vals = [_normalize_val(v) for v in df[col]]
            counts = {}
            for v in vals:
                counts[v] = counts.get(v, 0) + 1
            counters[col] = counts
        return counters

    g_counts = col_counter(gdf)
    c_counts = col_counter(cdf)

    matched = 0
    total = 0
    for col in common_cols:
        g_map = g_counts.get(col, {})
        c_map = c_counts.get(col, {})
        # compare by value frequency; allow tol for floats
        # exact match for non-floats; floats bucketed by rounded value (already rounded in _normalize_val)
        for val, gnum in g_map.items():
            cnum = c_map.get(val, 0)
            matched += min(gnum, cnum)
            total += gnum
    return matched / total if total else 0.0
