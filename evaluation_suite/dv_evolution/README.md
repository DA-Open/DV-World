# DV-Evolution Evaluation

## What it evaluates

This evaluator is for `dv-evol-*` cases.

It scores:

- visual similarity between candidate PNG and gold PNG
- table similarity between candidate CSV and gold CSV

Final score:

```text
score = vis_weight * visual_score + (1 - vis_weight) * table_score
```

## Inputs

- candidate results: `evaluation_suite/results/<run_name>/dv-evol-*`
- gold data: `dv-evolution/gold/dv-evol-*`

Each case should normally contain:

- `result.png`
- `result.csv` (optional but recommended)

## Run

Use:

```bash
python evaluation_suite/dv_evolution/run_eval.py \
  --inputs evaluation_suite/results/<run_name> \
  --gold-dir dv-evolution/gold \
  --out-dir evaluation_suite/model_score \
  --model gemini-2.5-flash
```

Useful optional flags:

- `--vis-weight 0.5`
- `--workers 10`

There is also a batch helper:

```bash
bash evaluation_suite/dv_evolution/run_eval.sh
```

## Output

The result JSON is written to:

```bash
evaluation_suite/model_score/<run_name>/dv-evol-results-<model>.json
```

It includes:

- per-case visual score
- per-case table score
- final score
- summary averages
