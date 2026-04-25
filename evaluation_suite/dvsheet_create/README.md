# DVSheet-Create Evaluation

## Environment

Run this evaluation on **Windows**.

This task works with Excel workbooks and related chart-export tooling, so Windows is the expected environment.

## What it evaluates

This evaluator is for `dvsheet-create-*` cases.

It evaluates:

- workbook/chart correctness through the rubric
- table correctness against the gold workbook
- final combined score

Supported score combination modes:

- `weighted`
- `product`

## Inputs

- candidate results: `evaluation_suite/results/<run_name>/dvsheet-create-*`
- gold data: `dv-sheet/gold/dvsheet-create-*`

Each candidate case should contain:

- a candidate Excel file (`.xlsx` or `.xls`)
- optionally a chart image such as `chart.png`

Each gold case should contain:

- a gold Excel file
- `query.md`
- `rubric.md`
- `metadata.json`

## Export chart images

Before evaluation, export chart images first:

```bash
python evaluation_suite/dvsheet_create/export_chart_png.py \
  --inputs evaluation_suite/results/<run_name> \
  --chart-index 1 \
  --out-name chart.png
```

What this script does:

- scans each `dvsheet-create-*` case under `--inputs`
- opens the workbook in Excel
- exports the selected chart as PNG
- writes the PNG back into the same case folder

Common options:

- `--chart-index 1`: export the first chart in the worksheet
- `--out-name chart.png`: output filename
- `--overwrite`: overwrite an existing PNG

## Run evaluation

After chart export is complete, run:

```bash
python evaluation_suite/dvsheet_create/run_eval.py \
  --inputs evaluation_suite/results/<run_name> \
  --gold-dir dv-sheet/gold \
  --out-dir evaluation_suite/model_score \
  --model gemini-2.5-flash
```

Useful optional flags:

- `--combine-mode weighted`
- `--vis-weight 0.5`
- `--table-weight 0.5`
- `--workers 1`

## Output

The result JSON is written to:

```bash
evaluation_suite/model_score/<run_name>/dvsheet-create-results-<model>.json
```

It includes:

- visual score
- table score
- combined score
- rubric dimension breakdown

## Notes

- Run this task on Windows.
- Evaluate only after chart export is finished.
- `export_chart_png.py` is the helper script for exporting chart images from candidate Excel files.