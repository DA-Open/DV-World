# DVSheet-Fix Evaluation

## Environment

Run this evaluation on **Windows**.

This task depends on Microsoft Excel / `xlwings` to inspect and compare workbook and chart state.

## What it evaluates

This evaluator is for `dvsheet-fix-*` cases.

It compares the candidate Excel workbook against the gold workbook.

When a broken workbook is available, it first infers the required fixes from `broken -> gold`, then checks whether the candidate fixed all required fields.

## Inputs

- candidate results: `evaluation_suite/results/<run_name>/dvsheet-fix-*`
- gold data: `dv-sheet/gold/dvsheet-fix-*`

Each candidate case should contain:

- a candidate Excel file (`.xlsx` or `.xls`)

Each gold case should contain:

- a gold Excel file
- optionally a broken workbook such as `*start*.xlsx` or `*broken*.xlsx`

## Run

Use:

```bash
python evaluation_suite/dvsheet_fix/run_eval.py \
  --inputs evaluation_suite/results/<run_name> \
  --gold-dir dv-sheet/gold \
  --out-dir evaluation_suite/model_score
```

Useful optional flags:

- `--broken-dir dv-sheet/gold`
- `--visible`
- `--workers 1`

If broken files are stored separately:

```bash
python evaluation_suite/dvsheet_fix/run_eval.py \
  --inputs evaluation_suite/results/<run_name> \
  --broken-dir evaluation_suite/broken \
  --gold-dir dv-sheet/gold \
  --out-dir evaluation_suite/model_score
```

## Output

The result JSON is written to:

```bash
evaluation_suite/model_score/<run_name>/dvsheet-fix-results.json
```

It includes:

- per-case score
- matched status
- summary average

## Notes

- Run this task on Windows.
- This task requires Microsoft Excel / xlwings.
- If either the candidate workbook or gold workbook is missing, the case is skipped.
- `--visible` is useful for debugging Excel-side issues.
