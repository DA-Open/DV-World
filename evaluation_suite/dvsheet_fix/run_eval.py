"""
Batch evaluator for DVSheet-Fix tasks (Candidate Excel vs Gold Excel).

Runs on Windows + Microsoft Excel (COM) via xlwings.

Example:
python evaluation_suite/dvsheet_fix/run_eval.py ^
  --inputs evaluation_suite/results/codex ^
  --gold-dir evaluation_suite/gold ^
  --out-dir evaluation_suite/model_score

Conventions:
- inputs/<case_id>/ contains a candidate .xlsx/.xls (first one found).
- gold-dir/<case_id>/ contains the gold .xlsx/.xls (first one found).
- case_id should start with "dvsheet-fix" to be evaluated.
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

from evaluation_suite.dvsheet_fix.evaluator import (  # noqa: E402
    evaluate_candidate_vs_gold,
    evaluate_candidate_with_broken,
    _as_jsonable,
)


def find_first_excel(case_dir: Path) -> Optional[Path]:
    for p in sorted(case_dir.iterdir()):
        if p.is_file() and p.suffix.lower() in {".xlsx", ".xls"}:
            return p
    return None


def _is_broken_filename(p: Path) -> bool:
    stem = p.stem.lower()
    return ("start" in stem) or ("broken" in stem)


def find_gold_and_broken(case_gold_dir: Path) -> tuple[Optional[Path], Optional[Path]]:
    """
    Convention (requested):
    - Gold dir contains both the gold xlsx and a broken version.
    - Detection rules: filenames containing gold are treated as gold; filenames containing start/broken are treated as broken; otherwise fall back to sorted order.
    """
    excels = [
        p
        for p in sorted(case_gold_dir.iterdir())
        if p.is_file() and p.suffix.lower() in {".xlsx", ".xls"}
    ]
    if not excels:
        return None, None

    broken_candidates = [p for p in excels if _is_broken_filename(p)]
    gold_candidates = [p for p in excels if "gold" in p.stem.lower()]

    broken = broken_candidates[0] if broken_candidates else None

    gold = None
    if gold_candidates:
        gold = gold_candidates[0]
    else:
        gold = next((p for p in excels if p not in broken_candidates), None)
        if gold is None and excels:
            gold = excels[0]

    return gold, broken


def _find_broken_only(case_dir: Path) -> Optional[Path]:
    excels = [
        p
        for p in sorted(case_dir.iterdir())
        if p.is_file() and p.suffix.lower() in {".xlsx", ".xls"}
    ]
    for p in excels:
        if _is_broken_filename(p):
            return p
    return None


def main():
    parser = argparse.ArgumentParser(description="Batch-evaluate DVSheet-Fix (candidate Excel vs gold Excel)")
    parser.add_argument("--inputs", required=True, type=Path, help="Candidate results directory; subdirectories are cases")
    parser.add_argument(
        "--broken-dir",
        type=Path,
        default="DV-Sheet/gold",
        help="Broken root directory, storing .xlsx files by <case_id> like gold. When provided, uses broken->gold to infer must-fix fields and applies a binary check.",
    )
    parser.add_argument("--gold-dir", type=Path, default=Path("DV-Sheet/gold"), help="Gold root directory")
    parser.add_argument(
        "--out-dir",
        dest="out_dir",
        type=Path,
        default=Path("evaluation_suite/model_score"),
        help="Output root directory; creates an inputs-named subdirectory and writes dvsheet-fix-results.json",
    )
    parser.add_argument("--visible", action="store_true", help="Debug mode: show the Excel window")
    parser.add_argument("--workers", type=int, default=1, help="Number of parallel evaluation workers")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_folder = args.out_dir / args.inputs.name
    out_folder.mkdir(parents=True, exist_ok=True)
    out_path = out_folder / "dvsheet-fix-results.json"

    def _eval_case(case_dir: Path) -> dict:
        case_id = case_dir.name
        cand_xlsx = find_first_excel(case_dir)
        case_gold_dir = args.gold_dir / case_id
        gold_xlsx, broken_in_gold = find_gold_and_broken(case_gold_dir)
        if not cand_xlsx or not gold_xlsx:
            return None
        broken_xlsx: Optional[Path] = None
        try:
            if args.broken_dir is not None:
                broken_xlsx = _find_broken_only(args.broken_dir / case_id)
                if not broken_xlsx:
                    broken_xlsx = find_first_excel(args.broken_dir / case_id)
                if not broken_xlsx:
                    raise FileNotFoundError(f"broken not found under {args.broken_dir / case_id}")
                res = evaluate_candidate_with_broken(cand_xlsx, broken_xlsx, gold_xlsx, visible=args.visible)
            elif broken_in_gold is not None:
                broken_xlsx = broken_in_gold
                res = evaluate_candidate_with_broken(cand_xlsx, broken_xlsx, gold_xlsx, visible=args.visible)
            else:
                res = evaluate_candidate_vs_gold(cand_xlsx, gold_xlsx, visible=args.visible)
            return {
                "case": case_id,
                "candidate": str(cand_xlsx),
                "broken": str(broken_xlsx) if broken_xlsx is not None else None,
                "gold": str(gold_xlsx),
                "score": res.score,
                "score_percent": res.score * 100,
                "matched": res.matched,
                "debug": res.debug,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "case": case_id,
                "candidate": str(cand_xlsx) if cand_xlsx else None,
                "gold": str(gold_xlsx) if gold_xlsx else None,
                "error": str(exc),
                "score": 0.0,
                "score_percent": 0.0,
            }

    cases = [p for p in args.inputs.iterdir() if p.is_dir() and p.name.startswith("dvsheet-fix")]
    results = []
    if args.workers and args.workers > 1:
        from concurrent.futures import ProcessPoolExecutor, as_completed
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            fut_to_case = {ex.submit(_eval_case, c): c.name for c in cases}
            for fut in as_completed(fut_to_case):
                rec = fut.result()
                if rec is None:
                    continue
                results.append(rec)
                print(f"[{rec['case']}] score={rec.get('score', 0.0)*100:.2f}% matched={rec.get('matched')}")
    else:
        for c in cases:
            rec = _eval_case(c)
            if rec is None:
                continue
            results.append(rec)
            print(f"[{rec['case']}] score={rec.get('score', 0.0)*100:.2f}% matched={rec.get('matched')}")

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(_as_jsonable(results), f, ensure_ascii=False, indent=2)

    total_cases = len(results)
    avg_score = sum(r.get("score", 0.0) or 0.0 for r in results) / total_cases if total_cases else 0.0
    summary = {
        "total_cases": total_cases,
        "avg_score": avg_score,
        "avg_score_percent": avg_score * 100,
    }
    # Append summary into JSON (keep backward compatibility by wrapping)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump({"results": _as_jsonable(results), "summary": summary}, f, ensure_ascii=False, indent=2)
    print(f"Wrote results to {out_path}; total cases: {total_cases}. Summary: score={avg_score*100:.3f}%")


if __name__ == "__main__":
    main()
