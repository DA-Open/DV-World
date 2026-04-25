"""
Batch-evaluate DVSheet Create tasks.

Usage example:
python evaluation_suite/dvsheet_create/run_eval.py \
  --inputs evaluation_suite/results/codex \
  --gold-dir evaluation_suite/gold \
  --out-dir evaluation_suite/model_score \
  --model gemini-2.5-flash

Output is written to an inputs-named subdirectory under out-dir, including results.json for all cases.

Conventions:
- Each inputs subdirectory is a case and contains the candidate Excel file.
- The first chart PNG/JPG, when present, is used as multimodal input; otherwise the visual score is 0.
- The gold directory stores query.md and rubric.md by case_id.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Dict, Any
from concurrent.futures import ProcessPoolExecutor, as_completed

from openpyxl import load_workbook


def _ensure_repo_on_path():
    root = Path(__file__).resolve().parents[2]
    sys.path.append(str(root))


_ensure_repo_on_path()

from evaluation_suite.dvsheet_create.evaluator import evaluate_task  # noqa: E402


def find_first(path: Path, exts) -> Optional[Path]:
    for p in sorted(path.iterdir()):
        if p.name.startswith(".~"):
            continue
        if p.suffix.lower() in exts and p.is_file():
            return p
    return None


def select_sheet(wb):
    for ws in wb.worksheets:
        if getattr(ws, "_charts", []):
            return ws
    return wb.active


def _eval_one(args_tuple):
    (
        case_dir,
        gold_dir,
        model,
        combine_mode,
        vis_weight,
        table_weight,
    ) = args_tuple

    case_id = case_dir.name
    wb_path = find_first(case_dir, {".xlsx", ".xls"})
    img_path = find_first(case_dir, {".png", ".jpg", ".jpeg"})
    query_path = gold_dir / case_id / "query.md"
    rubric_path = gold_dir / case_id / "rubric.md"
    meta_path = gold_dir / case_id / "metadata.json"

    if not (wb_path and query_path.exists() and rubric_path.exists() and meta_path.exists()):
        return None
    try:
        max_scores = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if "Total" not in max_scores:
        return None

    gold_wb_path = find_first(gold_dir / case_id, {".xlsx", ".xls"})
    wb = load_workbook(wb_path)
    ws = select_sheet(wb)

    res = evaluate_task(
        sheet=ws,
        query_text=query_path.read_text(encoding="utf-8"),
        rubric_text=rubric_path.read_text(encoding="utf-8"),
        max_scores=max_scores,
        task_type=case_id,
        workbook_path=wb_path,
        chart_img=img_path,
        model_name=model,
        gold_workbook=gold_wb_path,
        combine_mode=combine_mode,
        vis_weight=vis_weight,
        table_weight=table_weight,
    )

    return {
        "case": case_id,
        "workbook": str(wb_path),
        "chart_img": str(img_path) if img_path else None,
        "s_func": res.s_func,
        "s_func_percent": res.s_func * 100,
        "spatial_percent": res.spatial_score * 100,
        "dynamic_percent": res.dynamic_score * 100,
        "s_vis": res.s_vis,
        "s_vis_percent": res.s_vis * 100,
        "table_score": res.table_score,
        "table_percent": res.table_score * 100,
        "score": res.score,
        "score_percent": res.score * 100,
        "debug": res.debug,
        "model_raw": res.model_raw,
        "prompt": res.prompt_used,
        "vlm_total_raw": res.vlm_total_raw,
        "vlm_total_norm": res.vlm_total_norm,
        "vlm_total_percent": res.vlm_total_norm * 100,
        "vlm_dims_raw": res.vlm_dims_raw,
        "vlm_dims_norm": res.vlm_dims_norm,
        "vlm_dims_percent": {k: v * 100 for k, v in (res.vlm_dims_norm or {}).items()},
        "vlm_max_scores": res.vlm_max_scores,
        "gold_workbook": str(gold_wb_path) if gold_wb_path else None,
        "combine_mode": combine_mode,
        "vis_weight": vis_weight,
        "table_weight": table_weight,
    }


def main():
    parser = argparse.ArgumentParser(description="Batch-evaluate DVSheet Create tasks")
    parser.add_argument("--inputs", required=True, type=Path, help="Candidate results directory; subdirectories are cases")
    parser.add_argument("--gold-dir", type=Path, default="DV-Sheet/gold", help="Gold root directory")
    parser.add_argument("--out-dir", dest="out_dir", type=Path, default=Path("evaluation_suite/model_score"), help="Output root directory; creates an inputs-named subdirectory and writes results.json")
    parser.add_argument("--model", default="gemini-2.5-flash", help="Model config name")
    parser.add_argument(
        "--combine-mode",
        choices=["product", "weighted"],
        default="weighted",
        help="Score combine mode: product (default) or weighted (vis_weight*vis + table_weight*table).",
    )
    parser.add_argument("--vis-weight", type=float, default=0.5, help="Visual score weight when combine-mode=weighted.")
    parser.add_argument("--table-weight", type=float, default=0.5, help="Table score weight when combine-mode=weighted.")
    parser.add_argument("--workers", type=int, default=1, help="Number of parallel evaluation workers")
    args = parser.parse_args()

    results = []
    scores = []
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_folder = args.out_dir / args.inputs.name
    out_folder.mkdir(parents=True, exist_ok=True)
    model_tag = args.model.replace("/", "-").replace(":", "-").replace(" ", "-")
    out_path = out_folder / f"dvsheet-create-results-{model_tag}.json"

    agg_vis = []
    agg_table = []
    agg_score = []
    agg_dims: Dict[str, float] = {}

    case_dirs = [p for p in args.inputs.iterdir() if p.is_dir() and p.name.startswith("dvsheet-create")]
    tasks = [
        (case_dir, args.gold_dir, args.model, args.combine_mode, args.vis_weight, args.table_weight)
        for case_dir in sorted(case_dirs)
    ]

    if args.workers and args.workers > 1:
        from concurrent.futures import ProcessPoolExecutor, as_completed
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            fut_to_case = {ex.submit(_eval_one, t): t[0].name for t in tasks}
            for fut in as_completed(fut_to_case):
                case_id = fut_to_case[fut]
                rec = fut.result()
                if rec is None:
                    print(f"[{case_id}] skipped: missing workbook/query/rubric/metadata.")
                    continue
                results.append(rec)
    else:
        for t in tasks:
            rec = _eval_one(t)
            if rec is None:
                print(f"[{t[0].name}] skipped: missing workbook/query/rubric/metadata.")
                continue
            results.append(rec)

    for rec in results:
        agg_vis.append(rec["s_vis"])
        agg_table.append(rec["table_score"])
        agg_score.append(rec["score"])
        if isinstance(rec.get("vlm_dims_norm"), dict):
            for k, v in rec["vlm_dims_norm"].items():
                agg_dims[k] = agg_dims.get(k, 0.0) + float(v)
        dim_parts = []
        dims_norm = rec.get("vlm_dims_norm") or {}
        for k, v in dims_norm.items():
            dim_parts.append(f"{k}={v*100:.3f}%")
        dim_str = ", ".join(dim_parts) if dim_parts else ""
        if dim_str:
            dim_str = f"{dim_str}, vis-all={rec['s_vis']*100:.3f}%, table={rec['table_score']*100:.3f}%"
        else:
            dim_str = f"vis-all={rec['s_vis']*100:.3f}%, table={rec['table_score']*100:.3f}%"
        print(f"[{rec['case']}] score={rec['score']*100:.3f}% ({dim_str})")
        scores.append(rec["score"])

    total_cases = len(results)
    avg = sum(scores) / total_cases if total_cases else 0.0
    avg_vis = sum(agg_vis) / total_cases if total_cases else 0.0
    avg_table = sum(agg_table) / total_cases if total_cases else 0.0
    avg_dims = {k: v / total_cases for k, v in agg_dims.items()} if total_cases else {}
    summary: Dict[str, Any] = {
        "total_cases": total_cases,
        "avg_score": avg,
        "avg_score_percent": avg * 100,
        "avg_vis": avg_vis,
        "avg_vis_percent": avg_vis * 100,
        "avg_table": avg_table,
        "avg_table_percent": avg_table * 100,
        "avg_dims": avg_dims,
        "avg_dims_percent": {k: v * 100 for k, v in avg_dims.items()},
    }
    with out_path.open("w", encoding="utf-8") as f:
        json.dump({"results": results, "summary": summary}, f, ensure_ascii=False, indent=2)
    print(
        f"Wrote results to {out_path}; total cases: {total_cases}."
        f"Summary: score={avg*100:.3f}%, vis={avg_vis*100:.3f}%, table={avg_table*100:.3f}%"
        + (f", dims={{{', '.join(f'{k}={v*100:.3f}%' for k, v in avg_dims.items())}}}" if avg_dims else "")
    )


if __name__ == "__main__":
    main()
