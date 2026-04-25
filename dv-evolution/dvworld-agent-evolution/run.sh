#!/usr/bin/env bash
set -euo pipefail

TEST_PATH="../tasks/dv-evolution.jsonl"
MODEL="gpt-4o-2024-11-20" 
DATE_TAG="$(date +%m%d)"
TASK_NAME="evol"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --test_path) TEST_PATH="$2"; shift 2;;
    --model) MODEL="$2"; shift 2;;
    --date) DATE_TAG="$2"; shift 2;;
    --task) TASK_NAME="$2"; shift 2;;
    *) echo "Unknown arg: $1"; exit 1;;
  esac
done

LANGS=("python" "echarts" "vega-lite" "d3.js" "plotly.js")

for lang in "${LANGS[@]}"; do
  suffix="${TASK_NAME}-${DATE_TAG}-${lang}"
  echo "Running lang=${lang} suffix=${suffix}"
  python run.py \
    --test_path "${TEST_PATH}" \
    --model "${MODEL}" \
    --viz_lang "${lang}" \
    --suffix "${suffix}"
done
