#!/usr/bin/env python3
"""
Collect code line counts and evaluation scores for DV-Evol outputs.

For each target output directory (per model/language), this script:
1) finds the code file for each case (dv-evol-XXX) and counts lines
2) looks up the corresponding score_percent from the evaluation JSON
3) writes a CSV with model_dir, language, case_id, code_file, code_lines, score_percent

Defaults are tuned for the existing directory layout.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


# Known language suffixes -> code file name inside each case directory
LANG_FILE_MAP = {
    "echarts": "result.json",
    "vega-lite": "result.json",
    "python": "temp.py",
    "d3.js": "result.js",
    "plotly.js": "result.js",
}


def detect_language(dir_name: str) -> Optional[str]:
    for lang in LANG_FILE_MAP:
        if dir_name.endswith(lang):
            return lang
    return None


def load_score_map(score_json_path: Path) -> Dict[str, float]:
    try:
        data = json.loads(score_json_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    scores: Dict[str, float] = {}
    for rec in data.get("results", []):
        case_id = rec.get("case")
        if case_id:
            try:
                scores[case_id] = float(rec.get("score_percent", 0.0) or 0.0)
            except Exception:
                scores[case_id] = 0.0
    return scores


def find_score_file(eval_dir: Path) -> Optional[Path]:
    if not eval_dir.exists():
        return None
    candidates = sorted(eval_dir.glob("dv-evol-results-*.json"))
    return candidates[0] if candidates else None


def count_lines(path: Path) -> Optional[int]:
    try:
        return len(path.read_text(encoding="utf-8", errors="ignore").splitlines())
    except Exception:
        return None


def iter_target_dirs(
    output_root: Path, prefixes: Iterable[str]
) -> Iterable[Tuple[Path, str]]:
    prefix_set = list(prefixes)
    for p in sorted(output_root.iterdir()):
        if not p.is_dir():
            continue
        if not any(p.name.startswith(pref) for pref in prefix_set):
            continue
        lang = detect_language(p.name)
        if not lang:
            continue
        yield p, lang


def collect_rows(
    output_root: Path,
    eval_root: Path,
    prefixes: List[str],
) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for out_dir, lang in iter_target_dirs(output_root, prefixes):
        code_file = LANG_FILE_MAP[lang]
        eval_dir = eval_root / out_dir.name
        score_file = find_score_file(eval_dir)
        score_map = load_score_map(score_file) if score_file else {}
        for case_dir in sorted(out_dir.iterdir()):
            if not case_dir.is_dir() or not case_dir.name.startswith("dv-evol"):
                continue
            code_path = case_dir / code_file
            line_count = count_lines(code_path)
            rows.append(
                {
                    "model_dir": out_dir.name,
                    "language": lang,
                    "case_id": case_dir.name,
                    "code_file": str(code_path),
                    "code_lines": line_count,
                    "score_percent": score_map.get(case_dir.name),
                }
            )
    return rows


def main():
    parser = argparse.ArgumentParser(description="Collect code line counts and scores for DV-Evol outputs.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("DV-Evol/dvworld-agent/output"),
        help="Root directory containing model output folders.",
    )
    parser.add_argument(
        "--eval-root",
        type=Path,
        default=Path("evaluation_suite/model_score"),
        help="Root directory containing evaluation result JSONs.",
    )
    parser.add_argument(
        "--prefix",
        action="append",
        default=[
            "gemini-3-flash-preview-evol-0123",
            "gemini-2.5-pro-evol-0124",
            "gemini-3-pro-preview-new-evol-0123",
            "gpt-4.1-2025-04-14-evol-0124",
            "gpt-5.1-2025-04-14-evol-0123",
            "gpt-5.2-2025-12-11-evol-0123",
        ],
        help="Prefix of output directories to include (can be specified multiple times).",
    )
    parser.add_argument(
        "--out-csv",
        type=Path,
        default=Path("evaluation_suite/model_score/lines_and_scores.csv"),
        help="Destination CSV path.",
    )
    args = parser.parse_args()

    rows = collect_rows(args.output_root, args.eval_root, args.prefix)
    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["model_dir", "language", "case_id", "code_file", "code_lines", "score_percent"],
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {args.out_csv}")


if __name__ == "__main__":
    main()
