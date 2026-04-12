#!/usr/bin/env bash
set -euo pipefail

# glm-4.6v  doubao-seed-1-8-251215  Doubao-Seed-1.8  openai_qwen3-vl-plus  openai_qwen3-vl-235b-a22b-instruct  openai_qwen3-vl-32b-instruct    

TEST_PATH="/mnt/bn/mjx11/mlx/users/mengjinxiang/repo/DVSheet-1/DV-Evol/tasks/dv-evolution.jsonl"
MODEL="azure-grok-4"  # #gemini-3-pro-preview-new   gemini-2.5-pro   gpt-5.2-2025-12-11    gemini-3-flash-preview   azure-grok-4   gpt-4.1-2025-04-14
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
