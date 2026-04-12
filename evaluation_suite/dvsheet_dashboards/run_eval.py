"""
Batch evaluator for DVSheet-Dashboards tasks (rubric + multimodal LLM).

Workflow:
1) For each case in inputs, export the whole dashboard to PNG (Excel COM).
2) Run LLM judge with query + rubric + dashboard image.

Example (Windows):
python evaluation_suite/dvsheet_dashboards/run_eval.py ^
  --inputs evaluation_suite/results/codex ^
  --gold-dir evaluation_suite/gold ^
  --out-dir evaluation_suite/model_score ^
  --model gemini-2.5-flash
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional


def _ensure_repo_on_path():
    root = Path(__file__).resolve().parents[2]
    sys.path.append(str(root))


_ensure_repo_on_path()

from evaluation_suite.dvsheet_dashboards.evaluator import evaluate_dashboard  # noqa: E402
from evaluation_suite.dvsheet_dashboards.export_dashboard_png import (  # noqa: E402
    export_charts_via_com,
    find_workbook,
)
from evaluation_suite.dvsheet_dashboards.extract_dashboard_context import (  # noqa: E402
    context_to_text,
    extract_dashboard_context_via_com,
)
from evaluation_suite.dvsheet_dashboards.stitch_dashboard_png import stitch_dashboard_with_text_layer  # noqa: E402


def find_first(path: Path, exts) -> Optional[Path]:
    for p in sorted(path.iterdir()):
        if p.suffix.lower() in exts and p.is_file():
            return p
    return None


def _load_metadata(meta_path: Path) -> dict:
    """
    兼容不同缩进 / 额外空格 / BOM / 尾逗号的 metadata.json。
    """
    raw = meta_path.read_text(encoding="utf-8", errors="ignore")
    for loader in (
        lambda txt: json.loads(txt),
        lambda txt: json.loads(txt.encode("utf-8").decode("utf-8-sig")),
    ):
        try:
            return loader(raw)
        except Exception:
            pass
    # 尝试清理尾逗号与注释再解析
    cleaned = re.sub(r"//.*?$|/\\*.*?\\*/", "", raw, flags=re.MULTILINE | re.DOTALL)
    cleaned = re.sub(r",\\s*([}\\]])", r"\\1", cleaned)
    try:
        return json.loads(cleaned)
    except Exception:
        return {}


def main():
    parser = argparse.ArgumentParser(description="批量评估 DVSheet-Dashboards（rubric + LLM）")
    parser.add_argument("--inputs", required=True, type=Path, help="候选结果目录，子目录为 case")
    parser.add_argument("--gold-dir", type=Path, default=Path("DV-Sheet/gold"), help="gold 根目录")
    parser.add_argument(
        "--out-dir",
        dest="out_dir",
        type=Path,
        default=Path("evaluation_suite/model_score"),
        help="输出根目录（会在其中创建 inputs 同名子目录并写 dvsheet-dashboards-results.json）",
    )
    parser.add_argument("--model", default="gemini-2.5-flash", help="模型配置名")
    parser.add_argument("--sheet", default=None, help="指定导出工作表名（默认自动选择图表最多的可见表）")
    parser.add_argument("--out-prefix", default="dashboard_chart_", help="导出图片前缀（默认 dashboard_chart_）")
    parser.add_argument("--max-charts", type=int, default=0, help="最多导出多少个图表（0=不限制）")
    parser.add_argument("--visible", action="store_true", help="调试用：显示 Excel 窗口（默认隐藏）")
    parser.add_argument("--workers", type=int, default=1, help="并行评估进程数（默认1）")
    args = parser.parse_args()

    results = []
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_folder = args.out_dir / args.inputs.name
    out_folder.mkdir(parents=True, exist_ok=True)
    model_tag = args.model.replace("/", "-").replace(":", "-").replace(" ", "-")
    out_path = out_folder / f"dvsheet-dashboards-results-{model_tag}.json"

    from concurrent.futures import ProcessPoolExecutor, as_completed

    def _format_case(rec: dict) -> str:
        score = (rec.get("score") or 0.0) * 100
        dims_norm = rec.get("vlm_dims_norm") or {}
        # 如果没有归一化维度，则用 raw/max_scores 计算一次
        if not dims_norm:
            raw = rec.get("vlm_dims_raw") or {}
            mx = rec.get("vlm_max_scores") or {}
            dims_norm = {}
            for k, v in raw.items():
                max_v = mx.get(k)
                if max_v:
                    try:
                        dims_norm[k] = max(0.0, min(1.0, float(v) / float(max_v)))
                    except Exception:
                        continue
        dim_parts = [f"{k}={v*100:.2f}%" for k, v in dims_norm.items()]
        dim_str = ", ".join(dim_parts) if dim_parts else "dims: -"
        return f"[{rec.get('case')}] score={score:.2f}%, dims: {dim_str}"

    def _eval_one(case_dir: Path):
        case_id = case_dir.name
        if not case_id.startswith("dvsheet-dashboards"):
            return None

        wb_path = find_workbook(case_dir)
        if not wb_path:
            return None

        gold_case = args.gold_dir / case_id
        query_path = gold_case / "query.md"
        rubric_path = gold_case / "rubric.md"
        meta_path = gold_case / "metadata.json"
        if not (query_path.exists() and rubric_path.exists()):
            return None

        max_scores = {}
        if meta_path.exists():
            max_scores = _load_metadata(meta_path)

        try:
            existing = sorted(case_dir.glob(f"{args.out_prefix}*.png"))
            if existing:
                imgs = existing
            else:
                imgs = export_charts_via_com(
                    workbook_path=wb_path,
                    out_dir=case_dir,
                    sheet_name=args.sheet,
                    out_prefix=args.out_prefix,
                    max_charts=args.max_charts,
                    visible=args.visible,
                )
            if not imgs:
                raise RuntimeError("no charts exported from dashboard sheet")
        except Exception as exc:  # noqa: BLE001
            return {
                "case": case_id,
                "workbook": str(wb_path),
                "error": f"export_charts_failed: {exc}",
                "score": 0.0,
                "score_percent": 0.0,
            }

        stitched_path = None
        try:
            stitched_path = stitch_dashboard_with_text_layer(
                case_dir=case_dir,
                workbook_path=wb_path,
                out_name="dashboard_stitched.png",
                font_scale=1.35,
            )
        except Exception:
            stitched_path = None

        extracted_context_text = None
        try:
            ctx = extract_dashboard_context_via_com(
                wb_path,
                sheet_name=args.sheet,
            )
            extracted_context_text = context_to_text(ctx)
        except Exception as exc:  # noqa: BLE001
            extracted_context_text = f"extracted_context_error: {exc}"

        # Prefer stitched dashboard (tables/titles + chart overlays); fall back to per-chart images.
        imgs_for_llm = [stitched_path] if stitched_path is not None else imgs
        res = None
        last_exc = None
        for _ in range(3):
            try:
                res = evaluate_dashboard(
                    workbook_path=wb_path,
                    dashboard_imgs=imgs_for_llm,
                    extracted_context_text=extracted_context_text,
                    query_text=query_path.read_text(encoding="utf-8"),
                    rubric_text=rubric_path.read_text(encoding="utf-8"),
                    max_scores=max_scores,
                    model_name=args.model,
                )
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                import time
                time.sleep(0.5)
        if res is None:
            return {
                "case": case_id,
                "workbook": str(wb_path),
                "error": f"judge_failed: {last_exc}",
                "score": 0.0,
                "score_percent": 0.0,
            }

        rec = {
            "case": case_id,
            "workbook": str(wb_path),
            "dashboard_imgs": [str(p) for p in imgs],
            "dashboard_stitched": str(stitched_path) if stitched_path is not None else None,
            "score": res.score,
            "score_percent": res.score_percent,
            "debug": res.debug,
            "model_raw": res.model_raw,
            "prompt": res.prompt_used,
            "vlm_total_raw": res.vlm_total_raw,
            "vlm_total_norm": res.vlm_total_norm,
            "vlm_total_percent": res.vlm_total_norm * 100,
            "vlm_dims_raw": res.vlm_dims_raw,
            "vlm_dims_norm": res.vlm_dims_norm,
            "vlm_dims_percent": {k: v * 100 for k, v in (res.vlm_dims_norm or {}).items()},
            "vlm_max_scores": res.vlm_max_scores,
        }
        return rec

    case_dirs = sorted(p for p in args.inputs.iterdir() if p.is_dir())
    if args.workers and args.workers > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            fut_to_case = {ex.submit(_eval_one, case_dir): case_dir.name for case_dir in case_dirs}
            for fut in as_completed(fut_to_case):
                rec = fut.result()
                if rec:
                    results.append(rec)
                    print(_format_case(rec))
    else:
        for case_dir in case_dirs:
            rec = _eval_one(case_dir)
            if rec:
                results.append(rec)
                print(_format_case(rec))

    agg_score = [r.get("score", 0.0) or 0.0 for r in results]
    agg_dims = {}
    for r in results:
        if isinstance(r.get("vlm_dims_norm"), dict):
            for k, v in r["vlm_dims_norm"].items():
                agg_dims[k] = agg_dims.get(k, 0.0) + float(v)
    total_cases = len(results)
    avg_score = sum(agg_score) / total_cases if total_cases else 0.0
    avg_dims = {k: v / total_cases for k, v in agg_dims.items()} if total_cases else {}
    summary = {
        "total_cases": total_cases,
        "avg_score": avg_score,
        "avg_score_percent": avg_score * 100,
        "avg_dims": avg_dims,
        "avg_dims_percent": {k: v * 100 for k, v in avg_dims.items()},
    }

    with out_path.open("w", encoding="utf-8") as f:
        json.dump({"results": results, "summary": summary}, f, ensure_ascii=False, indent=2)
    print(
        f"写入结果到 {out_path}，共 {total_cases} 条。"
        f"汇总：score={avg_score*100:.3f}%"
        + (f", dims={{{', '.join(f'{k}={v*100:.3f}%' for k, v in avg_dims.items())}}}" if avg_dims else "")
    )


if __name__ == "__main__":
    main()
