
"""
Batch-export Excel charts to PNG under each task directory (Windows + Excel COM).
The export should match the Excel display as closely as possible.

Prerequisites: Windows, Microsoft Excel, and pywin32.

Usage example:
python evaluation_suite/dvsheet_create/export_chart_png.py \
  --inputs evaluation_suite/results/codex \
  --out-name chart.png \
  --chart-index 1
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Optional

import win32com.client as win32
import pythoncom


def _ensure_repo_on_path():
    root = Path(__file__).resolve().parents[2]
    sys.path.append(str(root))


_ensure_repo_on_path()


def find_workbook(case_dir: Path) -> Optional[Path]:
    for p in sorted(case_dir.iterdir()):
        if not p.is_file():
            continue
        name_lower = p.name.lower()
        # Skip Excel temp/lock files such as "~$foo.xlsx" or ".~foo.xlsx"
        if name_lower.startswith("~$") or name_lower.startswith(".~"):
            continue
        if p.suffix.lower() in {".xlsx", ".xls"} and p.stat().st_size > 0:
            return p
    return None


def export_chart_png(excel, ws, chart_obj, out_path: Path):
    """
    Export a chart as PNG while preserving the Excel display.
    """
    ws.Activate()
    time.sleep(0.1)
    
    try:
        chart_obj.Activate()
    except Exception:
        pass
    
    chart = chart_obj.Chart

    try:
        try:
            cat = chart.Axes(1, 1)
        except Exception:
            pass
        
        try:
            val = chart.Axes(2, 1)
        except Exception:
            pass
        
        try:
            if chart.HasAxis(1, 2):
                cat2 = chart.Axes(1, 2)
        except Exception:
            pass
        
        try:
            if chart.HasAxis(2, 2):
                val2 = chart.Axes(2, 2)
        except Exception:
            pass
            
    except Exception as e:
        print(f"  [warn] Failed to inspect axes: {e}")

    time.sleep(0.2)

    out_abs = str(out_path.resolve())
    chart.Export(Filename=out_abs, FilterName="PNG")


def export_charts_batch(cases, chart_index):
    pythoncom.CoInitialize()
    excel = win32.Dispatch("Excel.Application")
    
    excel.Visible = True
    excel.WindowState = -4140  # xlMinimized
    excel.DisplayAlerts = False
    excel.ScreenUpdating = True
    
    try:
        for workbook_path, out_path in cases:
            wb = None
            try:
                wb_abs = str(workbook_path.resolve())
                for attempt in (1, 2):
                    try:
                        wb = excel.Workbooks.Open(wb_abs)
                        break
                    except Exception as exc:
                        if attempt == 2:
                            raise
                        time.sleep(0.5)
                time.sleep(0.4)  # allow Excel to finish loading
                
                ws = None
                for sh in wb.Worksheets:
                    try:
                        if sh.ChartObjects().Count > 0:
                            ws = sh
                            break
                    except Exception:
                        continue
                
                if ws is None:
                    ws = wb.ActiveSheet
                
                charts = ws.ChartObjects()
                if charts.Count < chart_index:
                    raise IndexError(f"{ws.Name} has only {charts.Count} charts; index {chart_index} is out of range")
                
                chart_obj = charts.Item(chart_index)
                
                export_chart_png(excel, ws, chart_obj, out_path)
                
                print(f"[ok] {workbook_path.parent.name} -> {out_path.name}")
                
            except Exception as exc:
                print(f"[fail] {workbook_path.parent.name}: {exc}")
            finally:
                if wb:
                    try:
                        wb.Close(SaveChanges=False)
                    except Exception:
                        pass
                time.sleep(0.1)
    finally:
        try:
            excel.Quit()
        except Exception:
            pass
        pythoncom.CoUninitialize()


def main():
    parser = argparse.ArgumentParser(description="Batch-export Excel charts to PNG (Windows COM)")
    parser.add_argument("--inputs", required=True, type=Path, help="Candidate results directory; subdirectories are cases")
    parser.add_argument("--chart-index", type=int, default=1, help="One-based chart index to export; defaults to 1")
    parser.add_argument("--out-name", default="chart.png", help="Output filename saved under the case directory")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite an existing PNG with the same name; disabled by default.")
    args = parser.parse_args()

    cases = []
    for case_dir in sorted(p for p in args.inputs.iterdir() if p.is_dir() and p.name.startswith("dvsheet-create")):
        wb_path = find_workbook(case_dir)
        if not wb_path:
            print(f"[skip] {case_dir} Excel file not found")
            continue
        out_path = case_dir / args.out_name
        if (not args.overwrite) and out_path.exists():
            print(f"[skip] {case_dir} already exists: {args.out_name}; not overwritten.")
            continue
        cases.append((wb_path, out_path))

    if cases:
        export_charts_batch(cases, args.chart_index)


if __name__ == "__main__":
    main()
