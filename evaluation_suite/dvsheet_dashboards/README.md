# DVSheet-Dashboards Evaluation

## Environment

Run this evaluation on **Windows**.

This task requires Microsoft Excel because dashboard export and context extraction use Excel COM.

## What it evaluates

This evaluator is for `dvsheet-dashboards-*` cases.

It evaluates full dashboard workbooks with:

- exported dashboard chart images
- extracted dashboard context from Excel
- query, rubric, and metadata from the gold folder

## Inputs

- candidate results: `evaluation_suite/results/<run_name>/dvsheet-dashboards-*`
- gold data: `dv-sheet/gold/dvsheet-dashboards-*`

Each candidate case should contain:

- a dashboard Excel file (`.xlsx` or `.xls`)

Each gold case should contain:

- `query.md`
- `rubric.md`
- `metadata.json`

## Export dashboard images

Before evaluation, export dashboard chart images first:

```bash
python evaluation_suite/dvsheet_dashboards/export_dashboard_png.py \
  --inputs evaluation_suite/results/<run_name>
```

If you want to stitch the exported charts into one dashboard image:

```bash
python evaluation_suite/dvsheet_dashboards/stitch_dashboard_png.py \
  --case-dir evaluation_suite/results/<run_name>/dvsheet-dashboards-001
```

## Run evaluation

After chart export is complete, run:

```bash
python evaluation_suite/dvsheet_dashboards/run_eval.py \
  --inputs evaluation_suite/results/<run_name> \
  --gold-dir dv-sheet/gold \
  --out-dir evaluation_suite/model_score \
  --model gemini-2.5-flash
```

Useful optional flags:

- `--sheet Dashboard`
- `--out-prefix dashboard_chart_`
- `--max-charts 0`
- `--visible`
- `--workers 1`

## Output

The result JSON is written to:

```bash
evaluation_suite/model_score/<run_name>/dvsheet-dashboards-results-<model>.json
```

It includes:

- per-case score
- rubric dimension breakdown
- stitched dashboard image path when available

## Notes

- Run this task on Windows.
- This task requires Microsoft Excel for COM export.
- Evaluate only after dashboard export is finished.
- The evaluator prefers `dashboard_stitched.png` when available, and falls back to per-chart PNGs otherwise.
- `--visible` is useful when Excel export is blocked by a dialog or Protected View.
