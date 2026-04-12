"""
Batch evaluator for DV-Evolution tasks.

Evaluates case IDs starting with dv-evol:
- Compare candidate PNG vs gold PNG via VLM rubric.
- Compare candidate CSV vs gold CSV via cell match (0/1 similarity).
Final score = 0.5 * vis + 0.5 * table.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Dict, Any
from concurrent.futures import ProcessPoolExecutor, as_completed


def _ensure_repo_on_path():
    root = Path(__file__).resolve().parents[2]
    sys.path.append(str(root))


_ensure_repo_on_path()

from evaluation_suite.dv_evolution.evaluator import vlm_visual_score, table_similarity  # noqa: E402


def find_first(path: Path, names) -> Optional[Path]:
    for p in sorted(path.iterdir()):
        if p.is_file() and p.name in names:
            return p
    return None


def _eval_one(args_tuple):
    case_dir, gold_dir, model, vis_weight = args_tuple
    case_id = case_dir.name
    gold_case = gold_dir / case_id
    gold_img = find_first(gold_case, {"gold.png", "result.png"})
    gold_csv = find_first(gold_case, {"gold.csv", "result.csv"})
    cand_img = find_first(case_dir, {"result.png"})
    cand_csv = find_first(case_dir, {"result.csv"})

    if not gold_img or not cand_img:
        return {
            "case": case_id,
            "error": "missing images",
            "score": 0.0,
            "s_vis": 0.0,
            "s_table": 0.0,
            "s_vis_norm": 0.0,
            "dims": {},
            "dims_norm": {},
            "model_raw": "",
            "prompt": "",
        }

    task_context = f"case_id={case_id}"
    res = vlm_visual_score(
        gold_img=gold_img,
        cand_img=cand_img,
        model_name=model,
        task_context=task_context,
    )
    s_table = table_similarity(gold_csv, cand_csv) if gold_csv and cand_csv else 0.0
    vis_w = vis_weight
    table_w = 1.0 - vis_w
    vis_norm = res.s_vis if res.s_vis is not None else 0.0
    final_score = vis_w * vis_norm + table_w * s_table

    dims = res.dims or res.debug.get("dims") if isinstance(res.debug, dict) else {}
    dims_norm = getattr(res, "dims_norm", {}) or {}

    return {
        "case": case_id,
        "s_vis": res.s_vis,
        "s_table": s_table,
        "s_vis_norm": vis_norm,
        "score": final_score,
        "score_percent": final_score * 100,
        "gold_render": str(gold_img) if gold_img else None,
        "cand_render": str(cand_img) if cand_img else None,
        "gold_csv": str(gold_csv) if gold_csv else None,
        "cand_csv": str(cand_csv) if cand_csv else None,
        "debug": res.debug,
        "model_raw": res.model_raw,
        "prompt": res.prompt_used,
        "dims": dims,
        "dims_norm": dims_norm,
    }


def main():
    parser = argparse.ArgumentParser(description="Batch evaluate DV-Evolution tasks (chart2code).")
    parser.add_argument("--inputs", required=True, type=Path, help="Candidate results dir (subdirs are cases)")
    parser.add_argument("--gold-dir", type=Path, default="DV-Evol/gold", help="Gold root dir")
    parser.add_argument("--out-dir", dest="out_dir", type=Path, default=Path("evaluation_suite/model_score"), help="Output root dir")
    parser.add_argument("--model", default="gemini-2.5-flash", help="VLM model config key")  # 
    parser.add_argument("--vis-weight", type=float, default=0.5, help="Weight for visual score")
    parser.add_argument("--workers", type=int, default=10, help="Parallel workers for evaluation")
    args = parser.parse_args()

    results = []
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_folder = args.out_dir / args.inputs.name
    out_folder.mkdir(parents=True, exist_ok=True)
    model_tag = args.model.replace("/", "-").replace(":", "-").replace(" ", "-")
    out_path = out_folder / f"dv-evol-results-{model_tag}.json"

    agg_vis = []
    agg_table = []
    agg_score = []
    agg_dims: Dict[str, float] = {}
    dim_max = {"Dimension_1": 4.0, "Dimension_2": 6.0, "Dimension_3": 6.0}

    cases = [p for p in args.inputs.iterdir() if p.is_dir() and p.name.startswith("dv-evol")]
    task_args = [(case_dir, args.gold_dir, args.model, args.vis_weight) for case_dir in sorted(cases)]

    if args.workers and args.workers > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            fut_to_case = {ex.submit(_eval_one, t): t[0].name for t in task_args}
            for fut in as_completed(fut_to_case):
                case_id = fut_to_case[fut]
                try:
                    rec = fut.result()
                except Exception as exc:
                    rec = {"case": case_id, "error": str(exc), "score": 0.0, "s_vis": 0.0, "s_table": 0.0, "s_vis_norm": 0.0, "dims": {}, "dims_norm": {}}
                results.append(rec)
    else:
        for t in task_args:
            rec = _eval_one(t)
            results.append(rec)

    for rec in results:
        vis_norm = rec.get("s_vis_norm", 0.0) or 0.0
        s_table = rec.get("s_table", 0.0) or 0.0
        dims = rec.get("dims") or {}
        dims_norm = rec.get("dims_norm") or {}
        if (not dims_norm) and isinstance(dims, dict) and dims:
            dims_norm = {}
            for k, v in dims.items():
                max_v = dim_max.get(k)
                if max_v:
                    try:
                        dims_norm[k] = max(0.0, min(1.0, float(v) / max_v))
                    except Exception:
                        continue
        dim_parts = []
        if isinstance(dims_norm, dict) and dims_norm:
            for k, v in dims_norm.items():
                try:
                    val = float(v) * 100
                except Exception:
                    val = 0.0
                dim_parts.append(f"{k}={val:.2f}%")
        elif isinstance(dims, dict):
            for k, v in dims.items():
                try:
                    val = float(v)
                except Exception:
                    val = 0.0
                dim_parts.append(f"{k}={val:.2f}")
        dim_text = ", ".join(dim_parts) if dim_parts else "(no dim breakdown)"
        agg_vis.append(vis_norm)
        agg_table.append(s_table)
        agg_score.append(rec.get("score", 0.0) or 0.0)
        if isinstance(dims_norm, dict):
            for k, v in dims_norm.items():
                try:
                    agg_dims[k] = agg_dims.get(k, 0.0) + float(v)
                except Exception:
                    continue
        print(
            f"[{rec.get('case')}] dims: {dim_text} | vis={vis_norm*100:.2f}%, table={s_table*100:.2f}%, score={(rec.get('score',0.0))*100:.2f}%"
        )

    def _avg(vals):
        return sum(vals) / len(vals) if vals else 0.0

    total_cases = len(results)
    avg_vis = _avg(agg_vis)
    avg_table = _avg(agg_table)
    avg_score = _avg(agg_score)
    avg_dims = {k: v / total_cases for k, v in agg_dims.items()} if total_cases else {}
    summary: Dict[str, Any] = {
        "total_cases": total_cases,
        "avg_vis": avg_vis,
        "avg_vis_percent": avg_vis * 100,
        "avg_table": avg_table,
        "avg_table_percent": avg_table * 100,
        "avg_score": avg_score,
        "avg_score_percent": avg_score * 100,
        "avg_dims": avg_dims,
        "avg_dims_percent": {k: v * 100 for k, v in avg_dims.items()},
    }
    out_path.write_text(json.dumps({"results": results, "summary": summary}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"写入结果到 {out_path}，共 {total_cases} 条。汇总：vis={avg_vis*100:.2f}%, table={avg_table*100:.2f}%, score={avg_score*100:.2f}%"
    )


if __name__ == "__main__":
    main()
