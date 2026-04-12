#!/usr/bin/env bash
set -euo pipefail

# 批量评估同一模型的多个 DV-Evol 实验（按前缀匹配结果目录）。
# bash evaluation_suite/dv_evolution/run_eval.sh
# 快捷用法（示例）： bash evaluation_suite/dv_evolution/run_eval.sh gemini-3-flash-preview-evol-0122 --workers 4
# 可选参数：
#   --model <name>    指定 judge 模型（默认从目录名前缀截取 “-evol” 前的部分）
#   --gold <path>     gold 根目录（默认 DV-Evol/gold）
#   --out  <path>     输出根目录（默认 evaluation_suite/model_score）
#   --workers <n>     并行评估进程数（传给 run_eval.py）

# 可以直接在此处填写默认配置，无需命令行传参
PREFIX=${PREFIX:-"azure-grok-4-evol-0123"}   # gpt-5
MODEL=${MODEL:-"gemini-2.5-flash"}           # judge model   gemini-2.5-pro      gemini-3-flash-preview     gpt-4.1-2025-04-14     gpt-4o-2024-11-20   gemini-2.5-flash
GOLD_DIR=${GOLD_DIR:-"DV-Evol/gold"}
OUT_DIR=${OUT_DIR:-"evaluation_suite/model_score"}
WORKERS=${WORKERS:-4}
OVERWRITE=${OVERWRITE:-""}  # 传 "1" 启用覆盖

summary_log="$OUT_DIR/summary.log"
rm -f "$summary_log"

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
RESULTS_ROOT="$ROOT/evaluation_suite/results"

if [[ -z "$PREFIX" ]]; then
  matches=("$RESULTS_ROOT"/*evol*)
else
  matches=("$RESULTS_ROOT"/${PREFIX}*)
fi
if [[ ${#matches[@]} -eq 0 || ! -d ${matches[0]} ]]; then
  echo "No matching directories under $RESULTS_ROOT for prefix '$PREFIX'" >&2
  exit 1
fi

for dir in "${matches[@]}"; do
  [[ -d "$dir" ]] || continue
  base=$(basename "$dir")
  if [[ -z "$MODEL" ]]; then
    model_guess="${base%%-evol*}"
  else
    model_guess="$MODEL"
  fi
  echo "\n=== Evaluating $base (model=$model_guess) ==="
  python "$ROOT/evaluation_suite/dv_evolution/run_eval.py" \
    --inputs "$dir" \
    --gold-dir "$GOLD_DIR" \
    --out-dir "$OUT_DIR" \
    --model "$model_guess" \
    --workers "$WORKERS" \
    ${OVERWRITE:+--overwrite}
  # 记录最新的 summary 供汇总
  summary_json="$OUT_DIR/$base/dv-evol-results-${model_guess//[\\/: ]/-}.json"
  if [[ -f "$summary_json" ]]; then
    avg_score=$(python - "$summary_json" <<'PY'
import json, sys
path = sys.argv[1]
try:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    summary = data.get("summary") or {}
    val = summary.get("avg_score_percent")
    if val is None:
        val = summary.get("avg_score")
        if val is not None:
            val = val * 100
    if val is None:
        sys.exit(1)
    print(f"{val:.3f}%")
except Exception:
    sys.exit(1)
PY
    )
    if [[ -n "$avg_score" ]]; then
      echo "[SUMMARY] $base avg_score=${avg_score}" >> "$summary_log"
    fi
  fi
done

echo -e "\n=== 汇总 ==="
if [[ -f "$summary_log" ]]; then
  cat "$summary_log"
else
  echo "未找到 summary.log"
fi
