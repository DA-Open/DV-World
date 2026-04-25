"""
Batch-evaluate DV-Interact tasks with an image and trajectory LLM judge.

Usage example:
python evaluation_suite/dv-interact/run_eval.py \
  --inputs evaluation_suite/results/codex \
  --gold-dir evaluation_suite/gold \
  --out-dir evaluation_suite/model_score \
  --model gemini-2.5-flash

Conventions:
- Each subdirectory under inputs is a case, such as dv-interact-001, containing a candidate chart image and a trajectory file.
- The gold directory stores query.md, rubric.md, and metadata.json by case_id.
- Output is written under out-dir in a subdirectory named after inputs.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional


def _ensure_repo_on_path():
    root = Path(__file__).resolve().parents[2]
    sys.path.append(str(root))


_ensure_repo_on_path()

from evaluation_suite.dv_interact.evaluator import evaluate_task  # noqa: E402
from evaluation_suite.dv_interact.utils import load_trajectory_text  # noqa: E402


def find_first(path: Path, exts) -> Optional[Path]:
    for p in sorted(path.iterdir()):
        if p.suffix.lower() in exts and p.is_file():
            return p
    return None


def eval_case_worker(case_dir: Path, gold_dir: Path, model_name: str):
    case_id = case_dir.name
    img_path = find_first(case_dir, {".png", ".jpg", ".jpeg"})
    traj_path = find_first(case_dir, {".txt"})
    query_path = gold_dir / case_id / "query.md"
    rubric_path = gold_dir / case_id / "rubric.md"
    meta_path = gold_dir / case_id / "metadata.json"
    user_sim_path = case_dir / "user_simulation.json"

    def _zero_rec(reason: str):
        return {
            "case": case_id,
            "chart_img": str(img_path) if img_path else None,
            "trajectory": str(traj_path) if traj_path else None,
            "total_raw": 0.0,
            "total_percent": 0.0,
            "dim_scores": {},
            "dim_percents": {},
            "model_raw": reason,
            "prompt": "",
            "user_simulation": str(user_sim_path) if user_sim_path.exists() else None,
            "ask_user_calls": 0,
            "user_refusals": 0,
            "refusal_rate_percent": 0.0,
            "isr": 0.0,
            "final_score": 0.0,
        }

    if not traj_path:
        return _zero_rec("missing trajectory"), f"[{case_id}] missing trajectory -> 0"
    if not (query_path.exists() and rubric_path.exists()):
        return _zero_rec("missing query or rubric"), f"[{case_id}] missing query/rubric -> 0"
    if not meta_path.exists():
        return _zero_rec("missing metadata.json"), f"[{case_id}] missing metadata.json -> 0"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        total_points = float(meta["Total"])
        dim_max = {
            "Dimension_1": float(meta.get("Process", 0) or 0),
            "Dimension_2": float(meta.get("Correctness", 0) or 0),
            "Dimension_3": float(meta.get("Presentation", 0) or 0),
        }
    except Exception:
        return _zero_rec("malformed metadata"), f"[{case_id}] malformed metadata.json -> 0"

    traj_text = load_trajectory_text(traj_path)
    res = evaluate_task(
        query_text=query_path.read_text(encoding="utf-8"),
        rubric_text=rubric_path.read_text(encoding="utf-8"),
        trajectory_text=traj_text,
        chart_img=img_path if img_path and img_path.exists() else None,
        model_name=model_name,
        total_points=total_points,
        dim_max_scores=dim_max or None,
    )
    # user simulator stats
    ask_calls = 0
    refusals = 0
    if user_sim_path.exists():
        try:
            sim_data = json.loads(user_sim_path.read_text(encoding="utf-8"))
            ask_calls = int(sim_data.get("ask_user_calls", 0) or 0)
            refusals = int(sim_data.get("user_refusals", 0) or 0)
        except Exception:
            pass
    refusal_rate = round(refusals / ask_calls * 100, 2) if ask_calls > 0 else 0.0
    # ISR = 0.5 + 0.5 * (N_success - N_ref) / (N_req + 1)
    successes = max(ask_calls - refusals, 0)
    isr = 0.5 + 0.5 * (successes - refusals) / (ask_calls + 1)
    isr = max(min(isr, 1.0), 0.0)
    rubric_percent = round(res.total_norm * 100, 2)
    final_score = round(rubric_percent * isr, 2)
    dim_percents = {k: round(v * 100, 2) for k, v in (res.dim_percents or {}).items()}
    rec = {
        "case": case_id,
        "chart_img": str(img_path),
        "trajectory": str(traj_path),
        "total_raw": res.total_raw,
        "total_percent": rubric_percent,
        "dim_scores": res.dim_scores,
        "dim_percents": dim_percents,
        "model_raw": res.model_raw,
        "prompt": res.prompt_used,
        "user_simulation": str(user_sim_path) if user_sim_path.exists() else None,
        "ask_user_calls": ask_calls,
        "user_refusals": refusals,
        "refusal_rate_percent": refusal_rate,
        "isr": isr,
        "final_score": final_score,
    }
    return rec, None


def main():
    parser = argparse.ArgumentParser(description="Batch-evaluate DV-Interact tasks")
    parser.add_argument("--inputs", type=Path, default=Path("evaluation_suite/results/codex"), help="Candidate results directory; subdirectories are cases")
    parser.add_argument("--gold-dir", type=Path, default=Path("DV-Interact/gold"), help="Gold root directory")
    parser.add_argument("--out-dir", dest="out_dir", type=Path, default=Path("evaluation_suite/model_score"), help="Output root directory; creates an inputs-named subdirectory and writes results.json")
    parser.add_argument("--model", default="gemini-2.5-flash", help="Model config name")
    parser.add_argument("--workers", type=int, default=10, help="Number of parallel evaluation workers")
    args = parser.parse_args()

    results = []
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_folder = args.out_dir / args.inputs.name
    out_folder.mkdir(parents=True, exist_ok=True)
    model_tag = args.model.replace("/", "-").replace(":", "-").replace(" ", "-")
    out_path = out_folder / f"dv-interact-results-{model_tag}.json"

    case_dirs = sorted(p for p in args.inputs.iterdir() if p.is_dir() and p.name.startswith("dv-interact"))

    if args.workers and args.workers > 1:
        from concurrent.futures import ProcessPoolExecutor, as_completed
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            fut_map = {ex.submit(eval_case_worker, c, args.gold_dir, args.model): c.name for c in case_dirs}
            for fut in as_completed(fut_map):
                rec, msg = fut.result()
                if msg:
                    print(msg)
                    continue
                if rec:
                    results.append(rec)
                    dp = rec.get("dim_percents") or {}
                    dim_str = ", ".join(f"{k}={v:.2f}%" for k, v in dp.items()) if dp else "-"
                    print(
                        f"[{rec['case']}] final={rec['final_score']:.2f} "
                        f"(rubric={rec['total_percent']:.2f}, ISR={rec['isr']:.2f}) dims: {dim_str}"
                )
    else:
        for case_dir in case_dirs:
            rec, msg = eval_case_worker(case_dir, args.gold_dir, args.model)
            if msg:
                print(msg)
                continue
            if rec:
                results.append(rec)
                dp = rec.get("dim_percents") or {}
                dim_str = ", ".join(f"{k}={v:.2f}%" for k, v in dp.items()) if dp else "-"
                print(
                    f"[{rec['case']}] final={rec['final_score']:.2f} "
                    f"(rubric={rec['total_percent']:.2f}, ISR={rec['isr']:.2f}) dims: {dim_str}"
                )

    total_cases = len(results)
    sum_final = sum(r.get("final_score", 0.0) or 0.0 for r in results)
    sum_rubric = sum(r.get("total_percent", 0.0) or 0.0 for r in results)
    avg_isr = sum(r.get("isr", 0.0) or 0.0 for r in results) / total_cases if total_cases else 0.0
    dim_keys = set()
    for r in results:
        dim_keys.update((r.get("dim_percents") or {}).keys())
    avg_dims = {
        k: sum((r.get("dim_percents") or {}).get(k, 0.0) for r in results) / total_cases if total_cases else 0.0
        for k in sorted(dim_keys)
    }
    summary = {
        "total_cases": total_cases,
        "avg_final_percent": sum_final / total_cases if total_cases else 0.0,
        "avg_rubric_percent": sum_rubric / total_cases if total_cases else 0.0,
        "avg_isr": avg_isr,
        "avg_isr_percent": avg_isr * 100,
        "avg_dims_percent": avg_dims,
    }

    with out_path.open("w", encoding="utf-8") as f:
        json.dump({"results": results, "summary": summary}, f, ensure_ascii=False, indent=2)
    avg_dims_str = ", ".join(f"{k}={v:.2f}%" for k, v in avg_dims.items()) if avg_dims else "-"
    print(
        f"Wrote results to {out_path}; total cases: {total_cases}."
        f"Summary: final(with ISR)={summary['avg_final_percent']:.2f}%, rubric={summary['avg_rubric_percent']:.2f}%, "
        f"ISR={avg_isr*100:.2f}%, dims={avg_dims_str}"
    )


if __name__ == "__main__":
    main()
