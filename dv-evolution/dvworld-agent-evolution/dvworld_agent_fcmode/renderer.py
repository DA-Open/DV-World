"""
DVTransfer: render JS visualization code to image + extract plotted data.

Core idea:
- Wrap code/spec into an HTML template (CDN scripts injected)
- Use Playwright to open the page, wait for render, extract data, take screenshot

Supported tool types:
- echarts (chart.json: ECharts option)
- vega-lite (chart.json: Vega-Lite spec)
- plotly (chart.json: Plotly {data,layout,config} or fig-like)
- d3 (chart.js: D3 script that renders into #vis)

Notes:
- Requires network access to load CDN assets unless you replace with local bundles.
"""

from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


STATIC_LIB_DIR = Path(__file__).resolve().parent / "static" / "lib"


def _lib_uri(filename: str, fallback: str) -> str:
    """
    Prefer local bundled libs; fallback to CDN if not present.
    """
    local_path = STATIC_LIB_DIR / filename
    if local_path.exists():
        try:
            return local_path.as_uri()
        except Exception:
            return fallback
    return fallback


CDN = {
    "echarts": _lib_uri("echarts.min.js", "https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"),
    "vega": _lib_uri("vega.js", "https://cdn.jsdelivr.net/npm/vega@5"),
    "vega_lite": _lib_uri("vega-lite.js", "https://cdn.jsdelivr.net/npm/vega-lite@5"),
    "vega_embed": _lib_uri("vega-embed.js", "https://cdn.jsdelivr.net/npm/vega-embed@6"),
    "d3": _lib_uri("d3.v7.min.js", "https://d3js.org/d3.v7.min.js"),
    "plotly": _lib_uri("plotly.min.js", "https://cdn.plot.ly/plotly-2.27.0.min.js"),
}


@dataclass(frozen=True)
class RenderResult:
    ok: bool
    tool_type: str
    screenshot_path: Optional[Path]
    extracted: Dict[str, Any]
    error: str = ""


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _render_python_matplotlib(code_path: Path, out_png: Path) -> RenderResult:
    """
    Execute a Python/Matplotlib script and capture the plot as an image.
    - Forces Agg backend
    - Patches plt.show() to save to out_png
    - Best-effort data extraction from current axes
    """
    try:
        code = code_path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        return RenderResult(False, "python", None, {}, error=f"read_failed: {exc}")

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return RenderResult(False, "python", None, {}, error=f"missing_matplotlib: {exc}")

    out_png.parent.mkdir(parents=True, exist_ok=True)
    extracted: Dict[str, Any] = {}
    err = ""

    try:
        plt.close("all")

        def _to_py_floats(seq):
            vals = []
            try:
                for v in seq:
                    try:
                        vals.append(float(v))
                    except Exception:
                        continue
            except Exception:
                return vals
            return vals

        def _patched_show(*args, **kwargs):
            try:
                plt.savefig(out_png)
            except Exception as save_exc:  # noqa: BLE001
                raise RuntimeError(f"save_failed: {save_exc}") from save_exc

        plt.show = _patched_show  # type: ignore

        ns = {"plt": plt, "__name__": "__main__"}
        exec(compile(code, str(code_path), "exec"), ns, ns)  # noqa: S102

        if not out_png.exists():
            try:
                plt.savefig(out_png)
            except Exception as save_exc:  # noqa: BLE001
                err = f"save_failed: {save_exc}"

        try:
            ax = plt.gca()
            lines = ax.get_lines()
            extracted["line_y"] = [_to_py_floats(getattr(line, "get_ydata", lambda: [])()) for line in lines]
            extracted["line_x"] = [_to_py_floats(getattr(line, "get_xdata", lambda: [])()) for line in lines]
            rects = getattr(ax, "patches", []) or []
            extracted["rects"] = []
            for r in rects:
                try:
                    extracted["rects"].append(
                        {
                            "height": float(getattr(r, "get_height", lambda: None)() or 0.0),
                            "width": float(getattr(r, "get_width", lambda: None)() or 0.0),
                            "x": float(getattr(r, "get_x", lambda: None)() or 0.0),
                            "y": float(getattr(r, "get_y", lambda: None)() or 0.0),
                        }
                    )
                except Exception:  # noqa: BLE001
                    continue
        except Exception as exc:  # noqa: BLE001
            extracted["_extract_error"] = str(exc)
    except Exception as exc:  # noqa: BLE001
        err = f"python_exec_failed: {exc}"
    finally:
        try:
            plt.close("all")
        except Exception:
            pass

    ok = bool(out_png.exists()) and not err
    return RenderResult(ok, "python", out_png if out_png.exists() else None, extracted, error=err)


def _normalize_type(t: str) -> str:
    t = (t or "").strip().lower()
    if t in {"vega", "vega-lite", "vegalite", "vl"}:
        return "vega-lite"
    if t in {"echarts", "apache echarts"}:
        return "echarts"
    if t in {"d3", "d3.js", "d3js"}:
        return "d3"
    if t in {"plotly", "plotly.js", "plotlyjs"}:
        return "plotly"
    if t in {"python", "matplotlib", "mpl"}:
        return "python"
    return t


def _script_include(uri: str) -> str:
    """
    Use inline script if local file:// URI is present to avoid local resource blocking;
    otherwise return a normal script src tag.
    """
    if uri.startswith("file://"):
        try:
            path = Path(uri.replace("file://", "", 1))
            content = path.read_text(encoding="utf-8")
            return f"<script>\n{content}\n</script>"
        except Exception:
            return f'<script src="{uri}"></script>'
    return f'<script src="{uri}"></script>'


def _html_template(tool_type: str, code_or_spec: str, *, width: int = 900, height: int = 600) -> str:
    tool_type = _normalize_type(tool_type)
    if tool_type == "echarts":
        return textwrap.dedent(
            f"""
            <!doctype html>
            <html>
              <head>
                <meta charset="utf-8" />
                <style>
                  html, body {{ margin: 0; padding: 0; }}
                  #vis {{ width: {width}px; height: {height}px; }}
                </style>
                {_script_include(CDN["echarts"])}
              </head>
              <body>
                <div id="vis"></div>
                <script>
                  window.__dvtransfer = {{}};
                  const el = document.getElementById('vis');
                  try {{
                    const chart = echarts.init(el);
                    window.__dvtransfer.chart = chart;
                    const option = {code_or_spec};
                    chart.setOption(option, true);
                  }} catch (err) {{
                    window.__dvtransfer.error = String(err);
                  }}
                </script>
              </body>
            </html>
            """
        ).strip()

    if tool_type == "vega-lite":
        return textwrap.dedent(
            f"""
            <!doctype html>
            <html>
              <head>
                <meta charset="utf-8" />
                <style>
                  html, body {{ margin: 0; padding: 0; }}
                  /* Let Vega decide its own layout; we will crop screenshot to the rendered SVG/canvas. */
                  #vis {{ display: inline-block; }}
                </style>
                {_script_include(CDN["vega"])}
                {_script_include(CDN["vega_lite"])}
                {_script_include(CDN["vega_embed"])}
              </head>
              <body>
                <div id="vis"></div>
                <script>
                  window.__dvtransfer = {{}};
                  const spec = {code_or_spec};
                  vegaEmbed('#vis', spec, {{actions:false, renderer: 'svg'}})
                    .then(res => {{
                      window.__dvtransfer.view = res.view;
                      return res.view.runAsync();
                    }})
                    .catch(err => {{
                      window.__dvtransfer.error = String(err);
                    }});
                </script>
              </body>
            </html>
            """
        ).strip()

    if tool_type == "plotly":
        return textwrap.dedent(
            f"""
            <!doctype html>
            <html>
              <head>
                <meta charset="utf-8" />
                <style>
                  html, body {{ margin: 0; padding: 0; }}
                  #vis, #chart {{ width: {width}px; height: {height}px; }}
                </style>
                {_script_include(CDN["plotly"])}
              </head>
              <body>
                <div id="vis"></div>
                <div id="chart"></div>
                <script>
                  window.__dvtransfer = {{}};
                  const spec = {code_or_spec};
                  const gd = document.getElementById('vis') || document.getElementById('chart');
                  window.__dvtransfer.gd = gd;
                  let data = spec.data || spec.traces || spec;
                  let layout = spec.layout || {{}};
                  let config = spec.config || {{displayModeBar: false}};
                  Plotly.newPlot(gd, data, layout, config)
                    .then(() => {{ window.__dvtransfer.ready = true; }})
                    .catch(err => {{ window.__dvtransfer.error = String(err); }});
                </script>
              </body>
            </html>
            """
        ).strip()

    if tool_type == "d3":
        # Expect code to render into #vis
        return textwrap.dedent(
            f"""
            <!doctype html>
            <html>
              <head>
                <meta charset="utf-8" />
                <style>
                  html, body {{ margin: 0; padding: 0; }}
                  #vis, #my_dataviz, #chart {{ width: {width}px; height: {height}px; overflow: hidden; }}
                </style>
                {_script_include(CDN["d3"])}
              </head>
              <body>
                <div id="vis"></div>
                <div id="my_dataviz"></div>
                <div id="chart"></div>
                <script>
                  // Aliases for common snippets; create a chart container so d3.select('#chart') works.
                  const my_dataviz = document.getElementById('my_dataviz');
                  const chart = document.getElementById('chart');
                  const vis = document.getElementById('vis');
                  window.__dvtransfer = {{}};
                  window.__dvtransfer.root = my_dataviz || chart || vis || document.body;
                </script>
                <script>
                  try {{
                    {code_or_spec}
                    window.__dvtransfer.ready = true;
                  }} catch (err) {{
                    window.__dvtransfer.error = String(err);
                  }}
                </script>
              </body>
            </html>
            """
        ).strip()

    raise ValueError(f"Unsupported tool type: {tool_type}")


def _extract_script(tool_type: str) -> str:
    tool_type = _normalize_type(tool_type)
    if tool_type == "echarts":
        return textwrap.dedent(
            """
            (() => {
              const out = {};
              const chart = window.__dvtransfer && window.__dvtransfer.chart;
              if (!chart) { out.error = "missing echarts chart instance"; return out; }
              const opt = chart.getOption ? chart.getOption() : null;
              out.option = opt;
              // Best-effort "data"
              const series = (opt && opt.series) ? opt.series : [];
              out.series_data = series.map(s => s && (s.data ?? null));
              const dataset = (opt && opt.dataset) ? opt.dataset : null;
              out.dataset_source = dataset && (dataset.source ?? null);
              return out;
            })()
            """
        ).strip()

    if tool_type == "vega-lite":
        return textwrap.dedent(
            """
            (async () => {
              const out = {};
              const view = window.__dvtransfer && window.__dvtransfer.view;
              if (!view) { out.error = window.__dvtransfer?.error || "missing vega view"; return out; }
              try { await view.runAsync(); } catch (e) {}
              const rt = view._runtime && view._runtime.data ? view._runtime.data : {};
              const names = Object.keys(rt);
              out.data_names = names;
              out.datasets = {};
              for (const n of names) {
                try { out.datasets[n] = view.data(n); } catch (e) {}
              }
              return out;
            })()
            """
        ).strip()

    if tool_type == "plotly":
        return textwrap.dedent(
            """
            (() => {
              const out = {};
              const gd = window.__dvtransfer && window.__dvtransfer.gd;
              if (!gd) { out.error = window.__dvtransfer?.error || "missing plotly graph div"; return out; }
              out.data = gd.data || null;
              out.layout = gd.layout || null;
              return out;
            })()
            """
        ).strip()

    if tool_type == "d3":
        # Generic fallback: export SVG markup + bar heights if rects exist.
        return textwrap.dedent(
            """
            (() => {
              const out = {};
              if (window.__dvtransfer && window.__dvtransfer.error) {
                out.error = window.__dvtransfer.error;
              }
              const root =
                document.getElementById('my_dataviz') ||
                document.getElementById('chart') ||
                document.getElementById('vis') ||
                document.querySelector('svg')?.parentElement ||
                document.body;
              const svg = root ? root.querySelector('svg') : null;
              out.svg = svg ? svg.outerHTML : null;
              if (svg) {
                const rects = Array.from(svg.querySelectorAll('rect')).map(r => ({
                  x: r.getAttribute('x'),
                  y: r.getAttribute('y'),
                  width: r.getAttribute('width'),
                  height: r.getAttribute('height'),
                  fill: r.getAttribute('fill')
                }));
                out.rects = rects;
              } else if (!out.error) {
                out.error = "missing svg";
              }
              return out;
            })()
            """
        ).strip()

    raise ValueError(f"Unsupported tool type: {tool_type}")


def render_and_extract(
    *,
    tool_type: str,
    code_path: Path,
    out_png: Path,
    viewport: Tuple[int, int] = (1000, 700),
    timeout_ms: int = 20_000,
) -> RenderResult:
    """
    Render a single chart and extract data.
    """
    tool_type = _normalize_type(tool_type)
    if tool_type == "python":
        return _render_python_matplotlib(code_path, out_png)
    try:
        code_or_spec = code_path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        return RenderResult(False, tool_type, None, {}, error=f"read_failed: {exc}")

    spec_obj: Optional[Dict[str, Any]] = None
    if tool_type in {"echarts", "vega-lite", "plotly"}:
        try:
            spec_obj = json.loads(code_or_spec)
        except Exception:
            spec_obj = None

    # For canvas-based libs, align container size with viewport.
    # For Vega-Lite we crop to its rendered SVG, so container size doesn't matter.
    html = _html_template(tool_type, code_or_spec, width=viewport[0], height=viewport[1])

    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return RenderResult(False, tool_type, None, {}, error=f"missing_playwright: {exc}")

    out_png.parent.mkdir(parents=True, exist_ok=True)
    # Write html alongside outputs for debugging, but render via set_content to avoid
    # file:// navigation edge cases (which can destroy the JS execution context).
    html_path = out_png.with_suffix(".html")
    html_path.write_text(html, encoding="utf-8")

    def _trim_png(path: Path, pad: int = 6):
        """
        Remove large uniform margins (common when the render element is smaller than the viewport).
        Best-effort; failures are ignored.
        """
        try:
            from PIL import Image, ImageChops  # type: ignore
        except Exception:
            return
        try:
            im = Image.open(path)
        except Exception:
            return
        try:
            im = im.convert("RGB")
            w, h = im.size
            # Use the most common corner color as background.
            corners = [im.getpixel((0, 0)), im.getpixel((w - 1, 0)), im.getpixel((0, h - 1)), im.getpixel((w - 1, h - 1))]
            bg = max(set(corners), key=corners.count)
            bg_im = Image.new("RGB", im.size, bg)
            diff = ImageChops.difference(im, bg_im)
            bbox = diff.getbbox()
            if not bbox:
                return
            x0, y0, x1, y1 = bbox
            x0 = max(0, x0 - pad)
            y0 = max(0, y0 - pad)
            x1 = min(w, x1 + pad)
            y1 = min(h, y1 + pad)
            im.crop((x0, y0, x1, y1)).save(path)
        finally:
            try:
                im.close()
            except Exception:
                pass

    extracted: Dict[str, Any] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": viewport[0], "height": viewport[1]})
        console_lines: list[str] = []
        page_errors: list[str] = []
        page.on("console", lambda msg: console_lines.append(f"{msg.type}: {msg.text}"))
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        try:
            page.set_content(html, wait_until="load", timeout=timeout_ms)
            try:
                page.wait_for_load_state("networkidle", timeout=timeout_ms)
            except Exception:
                pass
            # Wait until render is likely complete.
            if tool_type == "vega-lite":
                page.wait_for_function("window.__dvtransfer && window.__dvtransfer.view", timeout=timeout_ms)
            elif tool_type == "echarts":
                page.wait_for_function("window.__dvtransfer && window.__dvtransfer.chart", timeout=timeout_ms)
            elif tool_type == "plotly":
                page.wait_for_function("window.__dvtransfer && window.__dvtransfer.gd && (window.__dvtransfer.ready || window.__dvtransfer.gd.data)", timeout=timeout_ms)
            elif tool_type == "d3":
                # Wait for an SVG/canvas to appear to avoid blank screenshots
                try:
                    page.wait_for_selector("svg, canvas", timeout=timeout_ms)
                except Exception:
                    page.wait_for_timeout(800)
            else:
                page.wait_for_timeout(800)

            # Prefer cropping to the actual rendered element to avoid large blank margins.
            selector = "#vis"
            if tool_type == "vega-lite":
                selector = "#vis svg, #vis canvas"
            elif tool_type == "echarts":
                selector = "#vis canvas"
            elif tool_type == "plotly":
                selector = (
                    "#vis .main-svg, #chart .main-svg, #vis svg, #chart svg, "
                    "#vis canvas, #chart canvas, svg, canvas"
                )
            elif tool_type == "d3":
                selector = (
                    "#my_dataviz svg, #chart svg, #vis svg, svg, "
                    "#my_dataviz canvas, #chart canvas, #vis canvas, canvas, "
                    "#chart, #my_dataviz, #vis"
                )
            try:
                loc = page.locator(selector)
                # For D3, the latest SVG/canvas is usually the rendered chart; prefer the last match.
                target = loc.last() if tool_type == "d3" else loc.first
                target.wait_for(state="attached", timeout=timeout_ms)
                target.screenshot(path=str(out_png))
            except Exception:
                page.screenshot(path=str(out_png), full_page=True)
            _trim_png(out_png)

            # Data extraction is best-effort; if it fails we still keep the render artifact
            # and allow visual scoring to proceed.
            def _ensure_ready_again():
                try:
                    if tool_type == "vega-lite":
                        page.wait_for_function("window.__dvtransfer && window.__dvtransfer.view", timeout=2000)
                    elif tool_type == "echarts":
                        page.wait_for_function("window.__dvtransfer && window.__dvtransfer.chart", timeout=2000)
                    elif tool_type == "plotly":
                        page.wait_for_function("window.__dvtransfer && window.__dvtransfer.gd", timeout=2000)
                except Exception:
                    pass

            extracted = {}
            last_err = ""
            for _ in range(3):
                try:
                    extracted = page.evaluate(_extract_script(tool_type))
                    last_err = ""
                    break
                except Exception as exc:  # noqa: BLE001
                    last_err = str(exc)
                    if "Execution context was destroyed" in last_err:
                        page.wait_for_timeout(200)
                        _ensure_ready_again()
                        continue
                    extracted = {"_extract_error": last_err}
                    break
            if last_err and not extracted:
                extracted = {"_extract_error": last_err}

            # Fallback: if Vega-Lite extraction failed/empty, try to recover data from the spec itself.
            def _flatten(obj):
                out = []
                if obj is None:
                    return out
                if isinstance(obj, (int, float)) and not isinstance(obj, bool):
                    out.append(float(obj))
                    return out
                if isinstance(obj, (list, tuple)):
                    for x in obj:
                        out.extend(_flatten(x))
                    return out
                if isinstance(obj, dict):
                    for v in obj.values():
                        out.extend(_flatten(v))
                    return out
                return out

            def _has_numbers(d: Dict[str, Any]) -> bool:
                return bool(_flatten(d))

            if tool_type == "vega-lite" and isinstance(spec_obj, dict):
                need_fill = not isinstance(extracted, dict) or not _has_numbers(extracted)
                if need_fill:
                    extracted = extracted if isinstance(extracted, dict) else {}
                    data_section = spec_obj.get("data") if isinstance(spec_obj, dict) else None
                    if isinstance(data_section, dict) and isinstance(data_section.get("values"), list):
                        extracted.setdefault("datasets", {})
                        extracted["datasets"]["__values_from_spec__"] = data_section["values"]
                    elif isinstance(spec_obj.get("datasets"), dict):
                        extracted.setdefault("datasets", {})
                        for k, v in spec_obj["datasets"].items():
                            extracted["datasets"][k] = v

            if isinstance(extracted, dict):
                if console_lines:
                    extracted["_console"] = console_lines[-200:]
                if page_errors:
                    extracted["_page_errors"] = page_errors[-50:]

            # "ok" means: the code produced a render we could capture.
            # If the page explicitly recorded a render error, treat as failed.
            render_err = None
            try:
                render_err = page.evaluate("window.__dvtransfer && window.__dvtransfer.error ? String(window.__dvtransfer.error) : ''")
            except Exception:
                render_err = ""

            ok = bool(out_png.exists()) and not bool(render_err)
            err_msg = str(render_err) if render_err else ""
            # Preserve extraction errors but don't flip ok.
            if isinstance(extracted, dict) and extracted.get("error") and not err_msg:
                err_msg = str(extracted.get("error"))

            return RenderResult(ok, tool_type, out_png if out_png.exists() else None, extracted, error=err_msg)
        except Exception as exc:  # noqa: BLE001
            # Best-effort: still write a screenshot for debugging.
            try:
                selector = "#vis"
                if tool_type == "d3":
                    selector = "#my_dataviz"
                loc = page.locator(selector)
                loc.screenshot(path=str(out_png))
            except Exception:
                try:
                    page.screenshot(path=str(out_png), full_page=True)
                except Exception:
                    pass
            if out_png.exists():
                _trim_png(out_png)

            if isinstance(extracted, dict):
                if console_lines:
                    extracted["_console"] = console_lines[-200:]
                if page_errors:
                    extracted["_page_errors"] = page_errors[-50:]
            if isinstance(extracted, dict) and "_page_errors" not in extracted and page_errors:
                extracted["_page_errors"] = page_errors[-50:]
            if isinstance(extracted, dict) and "_console" not in extracted and console_lines:
                extracted["_console"] = console_lines[-200:]

            shot = out_png if out_png.exists() else None
            return RenderResult(False, tool_type, shot, extracted, error=f"render_failed: {exc}")
        finally:
            try:
                page.close()
            except Exception:
                pass
            browser.close()


def load_case_type(case_dir: Path) -> str:
    """
    Read type.json. Accepts:
    - {"type": "echarts"} or {"type": "vega-lite"} ...
    """
    p = case_dir / "type.json"
    if not p.exists():
        return ""
    try:
        obj = _read_json(p)
    except Exception:
        return ""
    t = obj.get("type") or obj.get("target_lang") or ""
    return _normalize_type(str(t))


def find_code_file(case_dir: Path, tool_type: str) -> Optional[Path]:
    tool_type = _normalize_type(tool_type)
    if tool_type in {"echarts", "vega-lite", "plotly"}:
        p = case_dir / "chart.json"
        return p if p.exists() else None
    if tool_type == "d3":
        p = case_dir / "chart.js"
        return p if p.exists() else None
    if tool_type == "python":
        p = case_dir / "chart.py"
        return p if p.exists() else None
    # Fallback
    for p in sorted(case_dir.iterdir()):
        if p.is_file() and p.name.startswith("chart."):
            return p
    # Last resort: prefer .py, then .json/.js
    for suffix in (".py", ".json", ".js"):
        for p in sorted(case_dir.glob(f"*{suffix}")):
            if p.is_file():
                return p
    return None


__all__ = [
    "RenderResult",
    "render_and_extract",
    "load_case_type",
    "find_code_file",
]
