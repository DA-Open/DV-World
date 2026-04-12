"""
Extract dashboard context (tables + charts) from an Excel workbook via Excel COM.

This is intended to populate the `{chart_data}` field for rubric-based LLM judging:
- a small markdown snapshot of the dashboard sheet used range (tables)
- chart metadata and (sampled) series data

Runs on Windows + Microsoft Excel (COM) via pywin32.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


def _safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


def _safe_str(x: Any, default: str = "") -> str:
    try:
        if x is None:
            return default
        return str(x)
    except Exception:
        return default


def _truncate(s: str, limit: int) -> str:
    if len(s) <= limit:
        return s
    return s[: max(0, limit - 3)] + "..."


def _normalize_cell(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    # Format numeric types: floats to 2 decimals; ints as-is
    if isinstance(v, float):
        try:
            return f"{float(v):.2f}"
        except Exception:
            pass
    if isinstance(v, int):
        return str(v)
    # For string values that look like decimals, also format to 2 decimals.
    if isinstance(v, str):
        txt = v.strip()
        # Simple numeric check (optional sign, digits, optional decimal)
        import re

        if re.fullmatch(r"[+-]?\d+\.\d+", txt):
            try:
                return f"{float(txt):.2f}"
            except Exception:
                pass
        return _truncate(txt.replace("\r", " ").replace("\n", " "), 120)
    return _truncate(str(v).replace("\r", " ").replace("\n", " "), 120)


def _to_2d_list(values: Any) -> List[List[Any]]:
    """
    COM Range.Value may return:
    - scalar for 1 cell
    - tuple of tuples for multi-cell
    - tuple for 1 row/col
    """
    if values is None:
        return []
    if isinstance(values, (list, tuple)):
        # tuple of tuples
        if values and isinstance(values[0], (list, tuple)):
            return [list(r) for r in values]
        # single row/col
        return [list(values)]
    return [[values]]


def _markdown_table(grid: Sequence[Sequence[Any]], max_rows: int, max_cols: int) -> str:
    rows = list(grid)[:max_rows]
    if not rows:
        return ""
    # cap cols
    capped = [list(r)[:max_cols] for r in rows]
    # normalize to strings
    str_rows = [[_normalize_cell(c) for c in r] for r in capped]
    header = str_rows[0]
    md = ["| " + " | ".join(header) + " |", "|" + "|".join([" --- "] * len(header)) + "|"]
    for r in str_rows[1:]:
        md.append("| " + " | ".join(r) + " |")
    return "\n".join(md)


def _sample_sequence(seq: Any, max_points: int) -> List[Any]:
    if seq is None:
        return []
    # Excel returns tuple for series values/xvalues
    if isinstance(seq, (list, tuple)):
        flat: List[Any] = []
        for x in seq:
            if isinstance(x, (list, tuple)):
                flat.extend(list(x))
            else:
                flat.append(x)
        return flat[:max_points]
    return [seq]


@dataclass
class DashboardContext:
    sheet_name: str
    used_range_address: str
    used_rows: int
    used_cols: int
    table_markdown: str
    charts: List[Dict[str, Any]]


def select_dashboard_sheet(wb, sheet_name: Optional[str]):
    if sheet_name:
        return wb.Worksheets(sheet_name)

    def _sheet_score(ws) -> int:
        try:
            # Excel: -1=visible, 0=hidden, 2=very hidden
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

    best = None
    best_score = -10_000
    for ws in wb.Worksheets:
        s = _sheet_score(ws)
        if s > best_score:
            best = ws
            best_score = s
    return best if best is not None else wb.ActiveSheet


def extract_dashboard_context_via_com(
    workbook_path: Path,
    *,
    sheet_name: Optional[str] = None,
    max_table_rows: int = 0,
    max_table_cols: int = 0,
    max_charts: int = 0,
    max_series_per_chart: int = 0,
    max_points_per_series: int = 0,
) -> DashboardContext:
    """
    Extract a text-friendly dashboard context from Excel via COM.
    """
    import os

    if os.name != "nt":
        raise RuntimeError("Dashboard context extraction requires Windows (Excel COM).")

    import win32com.client as win32  # type: ignore
    import pythoncom  # type: ignore

    excel = None
    wb = None
    try:
        try:
            pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
        except Exception:
            pythoncom.CoInitialize()

        excel = win32.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        try:
            excel.ScreenUpdating = False
            excel.EnableEvents = False
            excel.AskToUpdateLinks = False
            try:
                excel.AutomationSecurity = 3
            except Exception:
                pass
        except Exception:
            pass

        wb = excel.Workbooks.Open(
            str(workbook_path.resolve()),
            UpdateLinks=0,
            ReadOnly=True,
            IgnoreReadOnlyRecommended=True,
            AddToMru=False,
        )
        ws = select_dashboard_sheet(wb, sheet_name)
        ws.Activate()

        ur = ws.UsedRange
        used_addr = _safe_str(getattr(ur, "Address", ""), "")
        used_rows = _safe_int(getattr(ur.Rows, "Count", 0), 0)
        used_cols = _safe_int(getattr(ur.Columns, "Count", 0), 0)

        # table snapshot
        r = max(1, used_rows)
        c = max(1, used_cols)
        if max_table_rows and max_table_rows > 0:
            r = min(r, max_table_rows)
        if max_table_cols and max_table_cols > 0:
            c = min(c, max_table_cols)
        table_rng = ws.Range(ur.Cells(1, 1), ur.Cells(r, c))
        table_grid = _to_2d_list(table_rng.Value)
        table_md = _markdown_table(
            table_grid,
            max_rows=(max_table_rows if max_table_rows and max_table_rows > 0 else 10**9),
            max_cols=(max_table_cols if max_table_cols and max_table_cols > 0 else 10**9),
        )

        charts: List[Dict[str, Any]] = []
        try:
            cos = ws.ChartObjects()
            count = _safe_int(cos.Count, 0)
            if max_charts and max_charts > 0:
                count = min(count, max_charts)
        except Exception:
            count = 0

        for i in range(1, count + 1):
            try:
                co = cos.Item(i)
                chart = co.Chart
            except Exception:
                continue

            title = ""
            try:
                if bool(chart.HasTitle):
                    title = _safe_str(chart.ChartTitle.Text, "")
            except Exception:
                title = ""

            ctype = None
            try:
                ctype = int(chart.ChartType)
            except Exception:
                ctype = None

            series_out: List[Dict[str, Any]] = []
            try:
                sc = chart.SeriesCollection()
                s_count = _safe_int(sc.Count, 0)
                if max_series_per_chart and max_series_per_chart > 0:
                    s_count = min(s_count, max_series_per_chart)
            except Exception:
                s_count = 0

            for si in range(1, s_count + 1):
                try:
                    ser = sc.Item(si)
                except Exception:
                    continue
                s_name = ""
                s_formula = ""
                try:
                    s_name = _safe_str(ser.Name, "")
                except Exception:
                    s_name = ""
                try:
                    s_formula = _safe_str(ser.Formula, "")
                except Exception:
                    s_formula = ""

                # Sample values/xvalues (can be expensive, so cap).
                x_sample: List[Any] = []
                y_sample: List[Any] = []
                try:
                    x_sample = _sample_sequence(ser.XValues, (max_points_per_series if max_points_per_series and max_points_per_series > 0 else 10**9))
                except Exception:
                    x_sample = []
                try:
                    y_sample = _sample_sequence(ser.Values, (max_points_per_series if max_points_per_series and max_points_per_series > 0 else 10**9))
                except Exception:
                    y_sample = []

                series_out.append(
                    {
                        "name": _truncate(s_name, 80),
                        "formula": _truncate(s_formula, 220),
                        "x_sample": [_normalize_cell(v) for v in x_sample],
                        "y_sample": [_normalize_cell(v) for v in y_sample],
                    }
                )

            charts.append(
                {
                    "index": i,
                    "title": _truncate(title, 120),
                    "chart_type": ctype,
                    "series": series_out,
                }
            )

        return DashboardContext(
            sheet_name=_safe_str(ws.Name, "Dashboard"),
            used_range_address=used_addr,
            used_rows=used_rows,
            used_cols=used_cols,
            table_markdown=table_md,
            charts=charts,
        )
    finally:
        try:
            if wb is not None:
                wb.Close(SaveChanges=False)
        except Exception:
            pass
        try:
            if excel is not None:
                excel.Quit()
        except Exception:
            pass
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass


def context_to_text(ctx: DashboardContext) -> str:
    lines: List[str] = []
    lines.append(f"dashboard_sheet: {ctx.sheet_name}")
    lines.append(f"used_range: {ctx.used_range_address} (rows={ctx.used_rows}, cols={ctx.used_cols})")
    if ctx.table_markdown:
        lines.append("")
        lines.append("table_preview_markdown:")
        lines.append(ctx.table_markdown)
    if ctx.charts:
        lines.append("")
        lines.append("charts:")
        for ch in ctx.charts:
            lines.append(f"- chart_{ch.get('index')}: type={ch.get('chart_type')}, title={ch.get('title')}")
            for si, ser in enumerate(ch.get("series") or [], start=1):
                lines.append(f"  - series_{si}: name={ser.get('name')}")
                lines.append(f"    formula={ser.get('formula')}")
                if ser.get("x_sample") or ser.get("y_sample"):
                    lines.append(f"    x_sample={ser.get('x_sample')}")
                    lines.append(f"    y_sample={ser.get('y_sample')}")
    return "\n".join(lines)


__all__ = ["DashboardContext", "extract_dashboard_context_via_com", "context_to_text"]
