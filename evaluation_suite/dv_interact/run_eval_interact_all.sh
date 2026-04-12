#!/usr/bin/env bash
set -euo pipefail

RESULTS_ROOT=${1:-evaluation_suite/results}
GOLD_DIR=${2:-DV-Interact/gold}
OUT_DIR=${3:-evaluation_suite/model_score}
MODEL_NAME=${4:-gemini-3-flash-preview}   #   gemini-2.5-pro      gemini-3-flash-preview     gpt-4.1-2025-04-14     gpt-4o-2024-11-20   gemini-2.5-flash
WORKERS=${5:-9}
MODEL_TAG=${MODEL_NAME//\//-}
MODEL_TAG=${MODEL_TAG//:/-}
MODEL_TAG=${MODEL_TAG// /-}

if [[ ! -d "$RESULTS_ROOT" ]]; then
  echo "Results root not found: $RESULTS_ROOT" >&2
  exit 1
fi

shopt -s nullglob
matched=0
out_paths=()
for input_dir in "$RESULTS_ROOT"/*gpt-4.1-2025-04-14-interact-0123*; do
  if [[ -d "$input_dir" ]]; then
    matched=1
    echo "Evaluating: $input_dir"
    python evaluation_suite/dv_interact/run_eval.py \
      --inputs "$input_dir" \
      --gold-dir "$GOLD_DIR" \
      --out-dir "$OUT_DIR" \
      --model "$MODEL_NAME" \
      --workers "$WORKERS"
    out_paths+=("$OUT_DIR/$(basename "$input_dir")/dv-interact-results-$MODEL_TAG.json")
  fi
done

if [[ $matched -eq 0 ]]; then
  echo "No interact result directories found under: $RESULTS_ROOT" >&2
  exit 2
fi

python - "$MODEL_NAME" "${out_paths[@]}" <<'PY'
import json
import sys
from pathlib import Path

model_name = sys.argv[1]
paths = [Path(p) for p in sys.argv[2:]]

all_results = []
missing = []
for p in paths:
    if not p.exists():
        missing.append(str(p))
        continue
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        missing.append(str(p))
        continue
    all_results.extend(data.get("results", []))

total_cases = len(all_results)
if total_cases == 0:
    print(f"[summary:{model_name}] no results to aggregate")
    if missing:
        print("[summary] missing files:")
        for m in missing:
            print(f" - {m}")
    raise SystemExit(0)

sum_final = sum(r.get("final_score", 0.0) or 0.0 for r in all_results)
sum_rubric = sum(r.get("total_percent", 0.0) or 0.0 for r in all_results)
avg_isr = sum(r.get("isr", 0.0) or 0.0 for r in all_results) / total_cases

dim_keys = set()
for r in all_results:
    dim_keys.update((r.get("dim_percents") or {}).keys())
avg_dims = {
    k: sum((r.get("dim_percents") or {}).get(k, 0.0) for r in all_results) / total_cases
    for k in sorted(dim_keys)
}

avg_dims_str = ", ".join(f"{k}={v:.2f}%" for k, v in avg_dims.items()) if avg_dims else "-"
print(
    f"[summary:{model_name}] cases={total_cases} "
    f"avg_final={sum_final/total_cases:.2f}% "
    f"avg_rubric={sum_rubric/total_cases:.2f}% "
    f"avg_ISR={avg_isr*100:.2f}% "
    f"dims={avg_dims_str}"
)

if missing:
    print("[summary] missing files:")
    for m in missing:
        print(f" - {m}")
PY
