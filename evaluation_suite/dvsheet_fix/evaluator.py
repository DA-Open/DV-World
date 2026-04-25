"""
DVSheet-Fix evaluator (Windows + Office + xlwings).

Goal: compare a "Candidate" Excel workbook vs a "Gold Standard" Excel workbook by
inspecting chart objects via Excel COM (through xlwings) and scoring similarity.

Why COM:
- openpyxl can't reliably evaluate how Excel interprets series bindings/axes.
- DVSheet-Fix focuses on repairing broken visualizations (series binding, axis scale, chart type).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


# -----------------------------
# Data structures
# -----------------------------


@dataclass(frozen=True)
class AxisSpec:
    minimum_is_auto: Optional[bool]
    maximum_is_auto: Optional[bool]
    minimum: Optional[float]
    maximum: Optional[float]


@dataclass(frozen=True)
class SeriesSpec:
    name: str
    name_expr: str
    formula: str
    categories_expr: str
    values_expr: str
    categories: List[Any]
    values: List[Any]


@dataclass(frozen=True)
class ChartSpec:
    sheet: str
    index: int  # 1-based within sheet
    chart_type: Optional[int]
    chart_type_group: str
    title: str
    plot_by: Optional[int]
    display_blanks_as: Optional[int]
    category_axis_type: Optional[int]
    value_axis_scale_type: Optional[int]
    series: List[SeriesSpec]
    axis_category: AxisSpec
    axis_value: AxisSpec


@dataclass(frozen=True)
class EvalResult:
    score: float
    matched: List[Dict[str, Any]]
    debug: Dict[str, Any]


# -----------------------------
# COM extraction
# -----------------------------


def _is_windows() -> bool:
    import os

    return os.name == "nt"


def chart_type_group(chart_type: Optional[int]) -> str:
    if chart_type is None:
        return "unknown"
    # Common Excel XlChartType constants (subset)
    line = {4, 65, 66, 63, 64}  # xlLine, xlLineMarkers, xlLineMarkersStacked, ...
    column = {51, 52, 53, 54, 57, 58, 59, 60}  # xlColumnClustered, xlColumnStacked, ...
    bar = {57, 58, 59, 60}
    pie = {5, 69, 70, 71}  # xlPie, xlPieExploded, ...
    scatter = {74, 75, 76, 77, 78, 79}  # xlXYScatter variants
    area = {1, 76, 77}  # rough
    if chart_type in line:
        return "line"
    if chart_type in column:
        return "column"
    if chart_type in bar:
        return "bar"
    if chart_type in pie:
        return "pie"
    if chart_type in scatter:
        return "scatter"
    if chart_type in area:
        return "area"
    return f"other:{chart_type}"


def _safe_get_axis_spec(chart: Any, axis_type: int) -> AxisSpec:
    """
    axis_type: 1=xlCategory, 2=xlValue
    """
    try:
        axis = chart.Axes(axis_type)
    except Exception:
        return AxisSpec(None, None, None, None)

    def _bool(prop: str) -> Optional[bool]:
        try:
            v = getattr(axis, prop)
            return bool(v)
        except Exception:
            return None

    def _float(prop: str) -> Optional[float]:
        try:
            v = getattr(axis, prop)
            if v is None:
                return None
            return float(v)
        except Exception:
            return None

    return AxisSpec(
        minimum_is_auto=_bool("MinimumScaleIsAuto"),
        maximum_is_auto=_bool("MaximumScaleIsAuto"),
        minimum=_float("MinimumScale"),
        maximum=_float("MaximumScale"),
    )


def _safe_get_int(obj: Any, attr: str) -> Optional[int]:
    try:
        v = getattr(obj, attr)
        if v is None:
            return None
        return int(v)
    except Exception:
        return None


def _safe_get_chart_axis_int(chart: Any, axis_type: int, attr: str) -> Optional[int]:
    try:
        axis = chart.Axes(axis_type)
    except Exception:
        return None
    return _safe_get_int(axis, attr)


def _normalize_range_address(addr: str) -> str:
    # xlwings can handle $ but normalizing reduces edge cases.
    return addr.replace("$", "")


_BOOK_PREFIX_RE = re.compile(r"^\s*\[[^\]]+\]")


def _parse_sheet_and_address(expr: str) -> Optional[Tuple[str, str]]:
    """
    Parse something like:
      'Sheet 1'!$A$2:$B$11
      [Book1]Sheet1!A1:B2
    Returns (sheet_name, a1_address) without $.
    """
    if "!" not in expr:
        return None
    sheet_part, addr = expr.split("!", 1)
    sheet_part = sheet_part.strip()
    sheet_part = _BOOK_PREFIX_RE.sub("", sheet_part).strip()
    if sheet_part.startswith("'") and sheet_part.endswith("'"):
        sheet_part = sheet_part[1:-1]
    return sheet_part, _normalize_range_address(addr.strip())


def _flatten_range_values(v: Any) -> List[Any]:
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        out: List[Any] = []
        for row in v:
            if isinstance(row, (list, tuple)):
                out.extend(list(row))
            else:
                out.append(row)
        return out
    return [v]


def _split_top_level_commas(s: str) -> List[str]:
    """
    Split by commas, but respect quoted strings.
    """
    parts: List[str] = []
    buf: List[str] = []
    in_quotes = False
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == '"':
            in_quotes = not in_quotes
            buf.append(ch)
            i += 1
            continue
        if ch == "," and not in_quotes:
            parts.append("".join(buf).strip())
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    if buf:
        parts.append("".join(buf).strip())
    return parts


def _parse_series_formula(formula: str) -> Tuple[str, str, str]:
    """
    Parse Excel's Series.Formula like:
      =SERIES(name,categories,values,order)
    Returns (name_expr, categories_expr, values_expr) as raw expressions.
    """
    if not formula:
        return "", "", ""
    m = re.match(r"^\s*=SERIES\((.*)\)\s*$", str(formula), flags=re.IGNORECASE)
    if not m:
        return "", "", ""
    inner = m.group(1)
    parts = _split_top_level_commas(inner)
    name_expr = parts[0] if len(parts) > 0 else ""
    cat_expr = parts[1] if len(parts) > 1 else ""
    val_expr = parts[2] if len(parts) > 2 else ""
    return name_expr, cat_expr, val_expr


def _parse_inline_array(expr: str) -> Optional[List[Any]]:
    """
    Best-effort parse of Excel inline arrays like:
      {1,2,3}
      {"A","B","C"}
    """
    expr = expr.strip()
    if not (expr.startswith("{") and expr.endswith("}")):
        return None
    inner = expr[1:-1].strip()
    if inner == "":
        return []
    # Handle both comma and semicolon separators (we flatten anyway).
    inner = inner.replace(";", ",")
    items = _split_top_level_commas(inner)
    out: List[Any] = []
    for it in items:
        it = it.strip()
        if it.startswith('"') and it.endswith('"'):
            out.append(it[1:-1])
            continue
        try:
            out.append(float(it))
        except Exception:
            out.append(it)
    return out


def _resolve_series_name(wb: Any, name_expr: str) -> str:
    """
    Resolve the SERIES() name expression to a display string, treating:
    - "Sales" (literal) and =Sheet1!B1 (cell ref containing "Sales") as equivalent.
    """
    vals = _try_resolve_expr_to_values(wb, name_expr)
    if not vals:
        return ""
    v = vals[0]
    if v is None:
        return ""
    return str(_norm_cell(v))


def _try_resolve_expr_to_values(wb: Any, expr: str) -> List[Any]:
    expr = str(expr or "").strip()
    if expr == "":
        return []
    if expr.startswith('"') and expr.endswith('"'):
        return [expr[1:-1]]
    arr = _parse_inline_array(expr)
    if arr is not None:
        return arr

    parsed = _parse_sheet_and_address(expr)
    if parsed is None:
        # Some Excel versions return "Sheet1!A1:B2" without quotes, or a bare name; keep as token.
        return [expr]

    sheet_name, addr = parsed
    try:
        rng = wb.sheets[sheet_name].range(addr)
        return _flatten_range_values(rng.value)
    except Exception:
        return [expr]


def extract_charts(workbook_path: Path, *, visible: bool = False) -> List[ChartSpec]:
    if not _is_windows():
        raise RuntimeError("DVSheet-Fix evaluator requires Windows (Excel COM via xlwings).")

    import xlwings as xw  # type: ignore

    specs: List[ChartSpec] = []
    app = xw.App(visible=visible, add_book=False)
    app.display_alerts = False
    app.screen_updating = False
    wb = None
    try:
        wb = app.books.open(str(workbook_path.resolve()), update_links=False, read_only=True)
        for sht in wb.sheets:
            try:
                chart_objects = sht.api.ChartObjects()
                count = int(chart_objects.Count)
            except Exception:
                continue

            for idx in range(1, count + 1):
                try:
                    chart = chart_objects.Item(idx).Chart
                except Exception:
                    continue

                try:
                    ctype = int(chart.ChartType)
                except Exception:
                    ctype = None

                title = ""
                try:
                    if bool(chart.HasTitle):
                        title = str(chart.ChartTitle.Text or "")
                except Exception:
                    title = ""

                series_specs: List[SeriesSpec] = []
                try:
                    sc = chart.SeriesCollection()
                    s_count = int(sc.Count)
                except Exception:
                    s_count = 0

                for s_idx in range(1, s_count + 1):
                    try:
                        ser = sc.Item(s_idx)
                    except Exception:
                        continue
                    try:
                        s_name_api = str(ser.Name or "")
                    except Exception:
                        s_name_api = ""
                    try:
                        s_formula = str(ser.Formula or "")
                    except Exception:
                        s_formula = ""

                    name_expr, cat_expr, val_expr = _parse_series_formula(s_formula)
                    s_name = _resolve_series_name(wb, name_expr) if name_expr else (s_name_api or "")
                    cats = _try_resolve_expr_to_values(wb, cat_expr)
                    vals = _try_resolve_expr_to_values(wb, val_expr)
                    series_specs.append(
                        SeriesSpec(
                            name=s_name,
                            name_expr=str(name_expr or ""),
                            formula=s_formula,
                            categories_expr=str(cat_expr or ""),
                            values_expr=str(val_expr or ""),
                            categories=cats,
                            values=vals,
                        )
                    )

                specs.append(
                    ChartSpec(
                        sheet=str(sht.name),
                        index=idx,
                        chart_type=ctype,
                        chart_type_group=chart_type_group(ctype),
                        title=title,
                        plot_by=_safe_get_int(chart, "PlotBy"),
                        display_blanks_as=_safe_get_int(chart, "DisplayBlanksAs"),
                        category_axis_type=_safe_get_chart_axis_int(chart, 1, "CategoryType"),
                        value_axis_scale_type=_safe_get_chart_axis_int(chart, 2, "ScaleType"),
                        series=series_specs,
                        axis_category=_safe_get_axis_spec(chart, 1),
                        axis_value=_safe_get_axis_spec(chart, 2),
                    )
                )
    finally:
        try:
            if wb is not None:
                wb.close()
        finally:
            app.quit()
    return specs


# -----------------------------
# Similarity
# -----------------------------


def _norm_cell(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, str):
        return v.strip()
    return v


def _is_number(v: Any) -> bool:
    if isinstance(v, bool):
        return False
    return isinstance(v, (int, float)) and not (isinstance(v, float) and (math.isnan(v) or math.isinf(v)))


def sequence_similarity(gold: Sequence[Any], cand: Sequence[Any]) -> float:
    g = [_norm_cell(x) for x in (gold or [])]
    c = [_norm_cell(x) for x in (cand or [])]
    if len(g) == 0 and len(c) == 0:
        return 1.0
    if len(g) == 0:
        return 0.0

    n = min(len(g), len(c))
    if n == 0:
        return 0.0

    matches = 0.0
    for i in range(n):
        gv, cv = g[i], c[i]
        if _is_number(gv) and _is_number(cv):
            tol = max(1e-6, 1e-4 * max(abs(float(gv)), 1.0))
            if abs(float(gv) - float(cv)) <= tol:
                matches += 1.0
        else:
            if str(gv) == str(cv):
                matches += 1.0

    base = matches / n
    # Penalize length mismatch.
    length_penalty = n / max(len(g), len(c))
    return base * length_penalty


def axis_similarity(g: AxisSpec, c: AxisSpec) -> float:
    if g.minimum_is_auto is None and g.maximum_is_auto is None:
        return 1.0

    def _auto_score(g_auto: Optional[bool], c_auto: Optional[bool]) -> float:
        if g_auto is None or c_auto is None:
            return 0.5
        return 1.0 if g_auto == c_auto else 0.0

    def _val_score(g_auto: Optional[bool], g_val: Optional[float], c_auto: Optional[bool], c_val: Optional[float]) -> float:
        if g_auto is True:
            return 1.0
        if g_auto is False:
            if c_auto is True:
                return 0.0
            if g_val is None or c_val is None:
                return 0.5
            tol = max(1e-6, 1e-3 * max(abs(g_val), 1.0))
            return 1.0 if abs(g_val - c_val) <= tol else 0.0
        return 0.5

    min_auto = _auto_score(g.minimum_is_auto, c.minimum_is_auto)
    max_auto = _auto_score(g.maximum_is_auto, c.maximum_is_auto)
    min_val = _val_score(g.minimum_is_auto, g.minimum, c.minimum_is_auto, c.minimum)
    max_val = _val_score(g.maximum_is_auto, g.maximum, c.maximum_is_auto, c.maximum)
    return 0.25 * (min_auto + max_auto + min_val + max_val)


def series_similarity(g: SeriesSpec, c: SeriesSpec) -> float:
    # Prefer data equality; fall back to formula similarity if data couldn't be resolved.
    cat_score = sequence_similarity(g.categories, c.categories)
    val_score = sequence_similarity(g.values, c.values)

    def _norm_formula(s: str) -> str:
        s = (s or "").strip()
        s = re.sub(r"\[[^\]]+\]", "", s)  # remove [Book]
        s = s.replace("$", "")
        s = re.sub(r"\s+", "", s)
        return s.lower()

    if cat_score == 0.0 and val_score == 0.0:
        gf = _norm_formula(g.formula)
        cf = _norm_formula(c.formula)
        if gf and cf and gf == cf:
            return 1.0
        # Very small partial credit if only one side has formula.
        return 0.0

    def _is_default_name(s: str) -> bool:
        s = (s or "").strip()
        return bool(re.match(r"^(series)\s*\d+$", s, flags=re.IGNORECASE))

    gn = (g.name or "").strip()
    cn = (c.name or "").strip()
    if gn.lower() == cn.lower() and gn != "":
        name_score = 1.0
    elif _is_default_name(gn) and _is_default_name(cn):
        name_score = 1.0
    elif not _is_default_name(gn) and not _is_default_name(cn):
        # Both are user-like names but differ; keep partial credit because some tasks
        # don't care about exact legend text.
        name_score = 0.5
    else:
        name_score = 0.0
    return 0.1 * name_score + 0.45 * cat_score + 0.45 * val_score


def chart_similarity(g: ChartSpec, c: ChartSpec) -> float:
    type_score = 1.0 if g.chart_type_group == c.chart_type_group else 0.0
    axis_score = 0.5 * axis_similarity(g.axis_category, c.axis_category) + 0.5 * axis_similarity(g.axis_value, c.axis_value)

    # Series matching (greedy; charts typically have few series)
    gold_series = list(g.series)
    cand_series = list(c.series)
    if not gold_series and not cand_series:
        series_score = 1.0
    elif not gold_series:
        series_score = 0.0
    else:
        used = set()
        total = 0.0
        for gs in gold_series:
            best = 0.0
            best_j = None
            for j, cs in enumerate(cand_series):
                if j in used:
                    continue
                s = series_similarity(gs, cs)
                if s > best:
                    best = s
                    best_j = j
            if best_j is not None:
                used.add(best_j)
            total += best
        # Penalize missing/extra series slightly.
        series_score = total / len(gold_series)
        series_score *= len(used) / max(len(gold_series), len(cand_series), 1)

    # Title is weak signal; many tasks won't touch it.
    title_score = 1.0 if (g.title or "").strip() == (c.title or "").strip() else 0.5
    return 0.2 * type_score + 0.6 * series_score + 0.15 * axis_score + 0.05 * title_score


def chart_component_scores(g: ChartSpec, c: ChartSpec) -> Dict[str, float]:
    """
    Return unweighted aspect scores in [0,1] to support must-fix gating.
    """
    type_score = 1.0 if g.chart_type_group == c.chart_type_group else 0.0
    plot_by_score = 1.0 if (g.plot_by is not None and c.plot_by is not None and g.plot_by == c.plot_by) else (1.0 if g.plot_by is None else 0.0)
    blanks_score = (
        1.0
        if (g.display_blanks_as is not None and c.display_blanks_as is not None and g.display_blanks_as == c.display_blanks_as)
        else (1.0 if g.display_blanks_as is None else 0.0)
    )
    cat_axis_type_score = (
        1.0
        if (g.category_axis_type is not None and c.category_axis_type is not None and g.category_axis_type == c.category_axis_type)
        else (1.0 if g.category_axis_type is None else 0.0)
    )
    val_scale_type_score = (
        1.0
        if (g.value_axis_scale_type is not None and c.value_axis_scale_type is not None and g.value_axis_scale_type == c.value_axis_scale_type)
        else (1.0 if g.value_axis_scale_type is None else 0.0)
    )
    axis_score = 0.5 * axis_similarity(g.axis_category, c.axis_category) + 0.5 * axis_similarity(g.axis_value, c.axis_value)

    # Series matching (same logic as chart_similarity, but expose raw series_score)
    gold_series = list(g.series)
    cand_series = list(c.series)
    if not gold_series and not cand_series:
        series_score = 1.0
    elif not gold_series:
        series_score = 0.0
    else:
        used = set()
        total = 0.0
        for gs in gold_series:
            best = 0.0
            best_j = None
            for j, cs in enumerate(cand_series):
                if j in used:
                    continue
                s = series_similarity(gs, cs)
                if s > best:
                    best = s
                    best_j = j
            if best_j is not None:
                used.add(best_j)
            total += best
        series_score = total / len(gold_series)
        series_score *= len(used) / max(len(gold_series), len(cand_series), 1)

    title_score = 1.0 if (g.title or "").strip() == (c.title or "").strip() else 0.5
    return {
        "type": type_score,
        "plot_by": plot_by_score,
        "display_blanks_as": blanks_score,
        "category_axis_type": cat_axis_type_score,
        "value_axis_scale_type": val_scale_type_score,
        "axis": axis_score,
        "series": series_score,
        "title": title_score,
    }


def evaluate_candidate_vs_gold(candidate_xlsx: Path, gold_xlsx: Path, *, visible: bool = False) -> EvalResult:
    cand = extract_charts(candidate_xlsx, visible=visible)
    gold = extract_charts(gold_xlsx, visible=visible)

    if not gold:
        return EvalResult(
            score=1.0 if not cand else 0.5,
            matched=[],
            debug={
                "note": "gold has no charts",
                "candidate_charts": len(cand),
                "gold_charts": len(gold),
            },
        )

    # Build all pair scores then greedy match highest.
    pairs: List[Tuple[float, int, int]] = []
    for gi, gc in enumerate(gold):
        for ci, cc in enumerate(cand):
            pairs.append((chart_similarity(gc, cc), gi, ci))
    pairs.sort(reverse=True, key=lambda x: x[0])

    used_g: set[int] = set()
    used_c: set[int] = set()
    matched: List[Dict[str, Any]] = []

    for s, gi, ci in pairs:
        if gi in used_g or ci in used_c:
            continue
        used_g.add(gi)
        used_c.add(ci)
        matched.append(
            {
                "gold": {"sheet": gold[gi].sheet, "index": gold[gi].index},
                "candidate": {"sheet": cand[ci].sheet, "index": cand[ci].index},
                "score": s,
            }
        )
        if len(used_g) == len(gold):
            break

    # Unmatched gold charts score as 0.
    sum_scores = sum(m["score"] for m in matched)
    base = sum_scores / len(gold)

    # Small penalty for extra candidate charts.
    extra = max(0, len(cand) - len(used_c))
    extra_penalty = min(0.10, 0.02 * extra)
    final = max(0.0, base * (1.0 - extra_penalty))

    debug = {
        "candidate_charts": len(cand),
        "gold_charts": len(gold),
        "matched_charts": len(matched),
        "extra_candidate_charts": extra,
        "extra_penalty": extra_penalty,
        "base_score": base,
    }

    # Add light chart details for debugging (avoid huge blobs).
    debug["gold_chart_ids"] = [f"{c.sheet}#{c.index}" for c in gold]
    debug["candidate_chart_ids"] = [f"{c.sheet}#{c.index}" for c in cand]
    return EvalResult(score=final, matched=matched, debug=debug)


def _greedy_match_by_similarity(gold: List[ChartSpec], other: List[ChartSpec]) -> Dict[int, Optional[int]]:
    """
    Return mapping gold_index -> other_index (indices are list indices, not chart indices).
    """
    if not gold:
        return {}
    if not other:
        return {gi: None for gi in range(len(gold))}

    pairs: List[Tuple[float, int, int]] = []
    for gi, g in enumerate(gold):
        for oi, o in enumerate(other):
            pairs.append((chart_similarity(g, o), gi, oi))
    pairs.sort(reverse=True, key=lambda x: x[0])

    used_g: set[int] = set()
    used_o: set[int] = set()
    match: Dict[int, Optional[int]] = {gi: None for gi in range(len(gold))}
    for s, gi, oi in pairs:
        if gi in used_g or oi in used_o:
            continue
        used_g.add(gi)
        used_o.add(oi)
        match[gi] = oi
        if len(used_g) == len(gold):
            break
    return match


def evaluate_candidate_with_broken(
    candidate_xlsx: Path,
    broken_xlsx: Path,
    gold_xlsx: Path,
    *,
    visible: bool = False,
    aspect_thresholds: Optional[Dict[str, float]] = None,
) -> EvalResult:
    """
    Hard-gate DVSheet-Fix using Broken as baseline:
    1) Determine which aspects must change by diffing Broken vs Gold.
    2) Candidate must match Gold on those aspects, otherwise score=0.

    Returns score in {0.0, 1.0}.
    """
    thresholds = {
        "type": 1.0,
        "plot_by": 1.0,
        "display_blanks_as": 1.0,
        "category_axis_type": 1.0,
        "value_axis_scale_type": 1.0,
        "series": 0.95,
    }
    if aspect_thresholds:
        thresholds.update(aspect_thresholds)

    cand = extract_charts(candidate_xlsx, visible=visible)
    broken = extract_charts(broken_xlsx, visible=visible)
    gold = extract_charts(gold_xlsx, visible=visible)

    if not gold:
        return EvalResult(score=0.0, matched=[], debug={"error": "gold has no charts"})

    match_broken = _greedy_match_by_similarity(gold, broken)
    match_cand = _greedy_match_by_similarity(gold, cand)

    all_ok = True
    matched: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []

    for gi, g in enumerate(gold):
        bi = match_broken.get(gi)
        ci = match_cand.get(gi)
        if bi is None or ci is None:
            all_ok = False
            failures.append(
                {
                    "gold": {"sheet": g.sheet, "index": g.index},
                    "reason": "unmatched chart",
                    "broken_matched": bi is not None,
                    "candidate_matched": ci is not None,
                }
            )
            continue

        b = broken[bi]
        c = cand[ci]
        bg = chart_component_scores(g, b)
        cg = chart_component_scores(g, c)

        must_fix = {k: True for k, v in bg.items() if k in thresholds and v < thresholds[k]}
        # title is intentionally not part of must-fix by default.
        must_fix.pop("title", None)

        chart_ok = True
        chart_fail: Dict[str, Any] = {"gold": {"sheet": g.sheet, "index": g.index}, "must_fix": sorted(must_fix.keys()), "fails": {}}
        for aspect in must_fix.keys():
            if cg.get(aspect, 0.0) < thresholds[aspect]:
                chart_ok = False
                chart_fail["fails"][aspect] = {"cand_vs_gold": cg.get(aspect, 0.0), "broken_vs_gold": bg.get(aspect, 0.0)}

        if not chart_ok:
            all_ok = False
            failures.append(chart_fail)

        matched.append(
            {
                "gold": {"sheet": g.sheet, "index": g.index},
                "broken": {"sheet": b.sheet, "index": b.index},
                "candidate": {"sheet": c.sheet, "index": c.index},
                "must_fix": sorted(must_fix.keys()),
                "broken_vs_gold": {k: bg[k] for k in sorted(must_fix.keys())},
                "candidate_vs_gold": {k: cg[k] for k in sorted(must_fix.keys())},
            }
        )

    return EvalResult(
        score=1.0 if all_ok else 0.0,
        matched=matched,
        debug={
            "mode": "broken-gated",
            "candidate_charts": len(cand),
            "broken_charts": len(broken),
            "gold_charts": len(gold),
            "thresholds": thresholds,
            "failures": failures,
        },
    )

def _as_jsonable(obj: Any) -> Any:
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _as_jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: _as_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_as_jsonable(v) for v in obj]
    return obj


__all__ = [
    "AxisSpec",
    "SeriesSpec",
    "ChartSpec",
    "EvalResult",
    "extract_charts",
    "evaluate_candidate_vs_gold",
    "evaluate_candidate_with_broken",
    "_as_jsonable",
]
