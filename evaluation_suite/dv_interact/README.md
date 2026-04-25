# DV-Interact Evaluation

## What it evaluates

This evaluator is for `dv-interact-*` cases.

It scores the task using:

- the final chart image
- the trajectory text
- the gold `query.md`
- the gold `rubric.md`
- the gold `metadata.json`

It also reads `user_simulation.json` when present and applies the ISR-style adjustment used in this task.

## Inputs

- candidate results: `evaluation_suite/results/<run_name>/dv-interact-*`
- gold data: `dv-interact/gold/dv-interact-*`

Each candidate case should contain:

- a chart image such as `result.png`
- a trajectory text file such as `*-traj.txt`

Each gold case should contain:

- `query.md`
- `rubric.md`
- `metadata.json`

## Run

Use:

```bash
python evaluation_suite/dv_interact/run_eval.py \
  --inputs evaluation_suite/results/<run_name> \
  --gold-dir dv-interact/gold \
  --out-dir evaluation_suite/model_score \
  --model gemini-2.5-flash
```

Useful optional flags:

- `--workers 10`

There is also a batch helper:

```bash
bash evaluation_suite/dv_interact/run_eval_interact_all.sh
```

## Output

The result JSON is written to:

```bash
evaluation_suite/model_score/<run_name>/dv-interact-results-<model>.json
```

It includes:

- rubric score
- dimension breakdown
- ISR
- final score after ISR adjustment
