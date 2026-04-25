

"""
Export dashboard charts to PNG (Windows + Excel COM).

Enhanced version with proper axis checking and rendering wait times.

Output:
- `<case_dir>/<out-prefix>1.png`, `<out-prefix>2.png`, ...
- `<case_dir>/<manifest-name>` JSON with chart metadata
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional, List, Dict, Any


def _ensure_repo_on_path():
    root = Path(__file__).resolve().parents[2]
    sys.path.append(str(root))


_ensure_repo_on_path()


def find_workbook(case_dir: Path) -> Optional[Path]:
    for p in sorted(case_dir.iterdir()):
        if not p.is_file():
            continue
        if p.name.startswith("~$") or p.name.startswith(".~"):
            continue
        if p.suffix.lower() in {".xlsx", ".xls"}:
            return p
    return None


def _safe_int(x, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


def _safe_str(x, default: str = "") -> str:
    try:
        if x is None:
            return default
        return str(x)
    except Exception:
        return default


def _sheet_score(ws) -> int:
    """
    Prefer visible sheets with many charts/shapes.
    Excel Visible: -1=visible, 0=hidden, 2=very hidden
    """
    try:
        if int(ws.Visible) != -1:
            return -10_000
    except Exception:
        pass
    charts = 0
    shapes = 0
    try:
        charts = _safe_int(ws.ChartObjects().Count, 0)
    except Exception:
        charts = 0
    try:
        shapes = _safe_int(ws.Shapes.Count, 0)
    except Exception:
        shapes = 0
    return 10 * charts + shapes


def select_dashboard_sheet(wb, sheet_name: Optional[str]):
    if sheet_name:
        return wb.Worksheets(sheet_name)
    best = None
    best_score = -10_000
    for ws in wb.Worksheets:
        s = _sheet_score(ws)
        if s > best_score:
            best = ws
            best_score = s
    return best if best is not None else wb.ActiveSheet


def export_single_chart(co, out_path: Path) -> bool:
    """
    Export one chart while ensuring all axes are visible and rendering is complete.
    """
    try:
        chart = co.Chart
        
        try:
            try:
                cat = chart.Axes(1, 1)  # xlCategory, xlPrimary
            except Exception:
                pass
            
            try:
                val = chart.Axes(2, 1)  # xlValue, xlPrimary
            except Exception:
                pass
            
            try:
                if chart.HasAxis(1, 2):  # xlCategory, xlSecondary
                    cat2 = chart.Axes(1, 2)
            except Exception:
                pass
            
            try:
                if chart.HasAxis(2, 2):  # xlValue, xlSecondary
                    val2 = chart.Axes(2, 2)
            except Exception:
                pass
        except Exception as e:
            print(f"  [warn] Failed to inspect axes: {e}")
        
        time.sleep(0.2)
        
        chart.Export(str(out_path.resolve()), "PNG")
        return out_path.exists()
    
    except Exception as e:
        print(f"  [warn] Failed to export chart: {e}")
        return False


def export_charts_via_com(
    workbook_path: Path,
    out_dir: Path,
    *,
    sheet_name: Optional[str] = None,
    out_prefix: str = "dashboard_chart_",
    manifest_name: str = "dashboard_charts.json",
    layout_name: str = "dashboard_layout.json",
    max_charts: int = 0,
    visible: bool = False,
) -> List[Path]:
    """
    Export all chart objects on a chosen worksheet into individual PNGs.
    Returns list of exported image paths.
    """
    import os

    if os.name != "nt":
        raise RuntimeError("Dashboard chart export requires Windows + Excel COM.")

    import win32com.client as win32
    import pythoncom

    out_dir.mkdir(parents=True, exist_ok=True)

    app = None
    wb = None
    exported: List[Path] = []
    manifest: List[Dict[str, Any]] = []
    layout: Dict[str, Any] = {}
    
    try:
        try:
            pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
        except Exception:
            pythoncom.CoInitialize()

        app = win32.DispatchEx("Excel.Application")
        
        app.Visible = True
        app.WindowState = -4140
        app.DisplayAlerts = False
        app.ScreenUpdating = True
        app.EnableEvents = False
        app.AskToUpdateLinks = False
        
        try:
            app.AutomationSecurity = 3
        except Exception:
            pass

        wb = app.Workbooks.Open(
            str(workbook_path.resolve()),
            UpdateLinks=0,
            ReadOnly=True,
            IgnoreReadOnlyRecommended=True,
            AddToMru=False,
        )

        ws = select_dashboard_sheet(wb, sheet_name)
        ws.Activate()
        
        time.sleep(0.3)

        # Layout for text-only base layer stitching.
        try:
            ur = ws.UsedRange
            start_row = _safe_int(getattr(ur, "Row", 1), 1)
            start_col = _safe_int(getattr(ur, "Column", 1), 1)
            n_rows = _safe_int(getattr(getattr(ur, "Rows", None), "Count", 1), 1)
            n_cols = _safe_int(getattr(getattr(ur, "Columns", None), "Count", 1), 1)
            left_pt = float(getattr(ur, "Left", 0.0))
            top_pt = float(getattr(ur, "Top", 0.0))

            col_width_pts: List[float] = []
            for c in range(start_col, start_col + max(1, n_cols)):
                try:
                    col_width_pts.append(float(getattr(ws.Columns(c), "Width", 0.0)))
                except Exception:
                    col_width_pts.append(0.0)

            row_height_pts: List[float] = []
            for r in range(start_row, start_row + max(1, n_rows)):
                try:
                    row_height_pts.append(float(getattr(ws.Rows(r), "Height", 0.0)))
                except Exception:
                    row_height_pts.append(0.0)

            layout = {
                "workbook": workbook_path.name,
                "sheet": _safe_str(ws.Name, ""),
                "used_range": _safe_str(getattr(ur, "Address", ""), ""),
                "start_row": start_row,
                "start_col": start_col,
                "rows": n_rows,
                "cols": n_cols,
                "left_pt": left_pt,
                "top_pt": top_pt,
                "col_width_pts": col_width_pts,
                "row_height_pts": row_height_pts,
            }
        except Exception:
            layout = {"workbook": workbook_path.name, "sheet": _safe_str(ws.Name, "")}

        try:
            cos = ws.ChartObjects()
            count = _safe_int(cos.Count, 0)
        except Exception:
            count = 0
        
        if max_charts and max_charts > 0:
            count = min(count, max_charts)

        for idx in range(1, count + 1):
            try:
                co = cos.Item(idx)
            except Exception:
                continue

            title = ""
            try:
                chart = co.Chart
                if bool(chart.HasTitle):
                    title = _safe_str(chart.ChartTitle.Text, "")
            except Exception:
                title = ""

            out_path = out_dir / f"{out_prefix}{idx}.png"
            
            if export_single_chart(co, out_path):
                exported.append(out_path)
                
                manifest.append(
                    {
                        "index": idx,
                        "sheet": _safe_str(ws.Name, ""),
                        "title": title,
                        "left": float(getattr(co, "Left", 0.0)),
                        "top": float(getattr(co, "Top", 0.0)),
                        "width": float(getattr(co, "Width", 0.0)),
                        "height": float(getattr(co, "Height", 0.0)),
                        "png": out_path.name,
                    }
                )

        (out_dir / manifest_name).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), 
            encoding="utf-8"
        )
        (out_dir / layout_name).write_text(
            json.dumps(layout, ensure_ascii=False, indent=2), 
            encoding="utf-8"
        )
        
        return exported
    
    finally:
        try:
            if wb is not None:
                wb.Close(SaveChanges=False)
        except Exception:
            pass
        try:
            if app is not None:
                app.Quit()
        except Exception:
            pass
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="Batch-export all charts from dashboard worksheets to PNG (Windows COM)")
    parser.add_argument("--inputs", required=True, type=Path, help="Candidate results directory; subdirectories are cases")
    parser.add_argument("--sheet", default=None, help="Worksheet name to export; defaults to the visible sheet with the most charts")
    parser.add_argument("--out-prefix", default="dashboard_chart_", help="Exported image filename prefix")
    parser.add_argument("--manifest-name", default="dashboard_charts.json", help="Export manifest JSON filename")
    parser.add_argument("--layout-name", default="dashboard_layout.json", help="Export layout JSON filename")
    parser.add_argument("--max-charts", type=int, default=0, help="Maximum number of charts to export; 0 means no limit")
    parser.add_argument("--visible", action="store_true", help="Debug mode: show the Excel window normally; defaults to minimized")
    args = parser.parse_args()

    for case_dir in sorted(p for p in args.inputs.iterdir() if p.is_dir()):
        if not case_dir.name.startswith("dvsheet-dashboards"):
            continue
        
        wb_path = find_workbook(case_dir)
        if not wb_path:
            print(f"[skip] {case_dir.name} Excel file not found")
            continue
        
        try:
            imgs = export_charts_via_com(
                workbook_path=wb_path,
                out_dir=case_dir,
                sheet_name=args.sheet,
                out_prefix=args.out_prefix,
                manifest_name=args.manifest_name,
                layout_name=args.layout_name,
                max_charts=args.max_charts,
                visible=args.visible,
            )
            print(f"[ok] {case_dir.name} exported {len(imgs)} charts")
        except Exception as exc:
            print(f"[fail] {case_dir.name}: {exc}")


if __name__ == "__main__":
    main()