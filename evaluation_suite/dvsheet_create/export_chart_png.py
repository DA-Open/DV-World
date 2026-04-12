# """
# 批量导出 Excel 图表为 PNG，存放在对应任务目录下（Windows + Excel COM）。

# 前置条件：Windows + Microsoft Excel + pywin32（pip install pywin32）。

# 用法示例：
# python evaluation_suite/dvsheet_create/export_chart_png.py \
#   --inputs evaluation_suite/results/codex \
#   --out-name chart.png \
#   --chart-index 1
# """

# from __future__ import annotations

# import argparse
# import sys
# import time
# from pathlib import Path
# from typing import Optional

# import win32com.client as win32
# import pythoncom


# def _ensure_repo_on_path():
#     root = Path(__file__).resolve().parents[2]
#     sys.path.append(str(root))


# _ensure_repo_on_path()


# def find_workbook(case_dir: Path) -> Optional[Path]:
#     for p in sorted(case_dir.iterdir()):
#         if p.is_file() and p.suffix.lower() in {".xlsx", ".xls"}:
#             return p
#     return None


# def export_charts_batch(cases: list[tuple[Path, Path]], chart_index: int):
#     """
#     批量导出图表，复用同一个 Excel 实例。
#     """
#     pythoncom.CoInitialize()
#     excel = win32.Dispatch("Excel.Application")
#     excel.Visible = False
#     excel.DisplayAlerts = False
#     excel.ScreenUpdating = False

#     try:
#         for workbook_path, out_path in cases:
#             wb = None
#             try:
#                 abs_path = str(workbook_path.resolve())
#                 wb = excel.Workbooks.Open(abs_path)
#                 if wb is None:
#                     raise RuntimeError(f"Excel 无法打开工作簿: {abs_path}")

#                 # 等待工作簿完全加载
#                 time.sleep(0.2)

#                 # 选择首个含图表的表
#                 ws = None
#                 for sh in wb.Worksheets:
#                     try:
#                         if sh.ChartObjects().Count > 0:
#                             ws = sh
#                             break
#                     except Exception:
#                         continue
#                 if ws is None:
#                     ws = wb.ActiveSheet

#                 charts = ws.ChartObjects()
#                 if charts.Count < chart_index:
#                     raise IndexError(f"工作表 {ws.Name} 只有 {charts.Count} 个图表，索引 {chart_index} 越界")

#                 chart_obj = charts.Item(chart_index)
#                 chart = chart_obj.Chart

#                 # 使用 Export 方法，指定 FilterName 为 PNG
#                 out_abs = str(out_path.resolve())
#                 chart.Export(Filename=out_abs, FilterName="PNG")

#                 print(f"[ok] {workbook_path.parent.name} -> {out_path.name}")

#             except Exception as exc:
#                 print(f"[fail] {workbook_path.parent.name}: {exc}")
#             finally:
#                 if wb is not None:
#                     try:
#                         wb.Close(SaveChanges=False)
#                     except Exception:
#                         pass
#                 # 每个文件处理后稍作等待，避免 COM 对象失效
#                 time.sleep(0.1)
#     finally:
#         try:
#             excel.Quit()
#         except Exception:
#             pass
#         pythoncom.CoUninitialize()


# def main():
#     parser = argparse.ArgumentParser(description="批量导出 Excel 图表为 PNG（Windows COM）")
#     parser.add_argument("--inputs", required=True, type=Path, help="候选结果目录，子目录为 case")
#     parser.add_argument("--chart-index", type=int, default=1, help="导出第几个图表，1 基，默认 1")
#     parser.add_argument("--out-name", default="chart.png", help="导出文件名，保存在 case 目录下")
#     args = parser.parse_args()

#     cases = []
#     for case_dir in sorted(p for p in args.inputs.iterdir() if p.is_dir()):
#         wb_path = find_workbook(case_dir)
#         if not wb_path:
#             print(f"[skip] {case_dir} 未找到 Excel 文件")
#             continue
#         out_path = case_dir / args.out_name
#         cases.append((wb_path, out_path))

#     if cases:
#         export_charts_batch(cases, args.chart_index)


# if __name__ == "__main__":
#     main()




# """
# 批量导出 Excel 图表为 PNG，存放在对应任务目录下（Windows + Excel COM）。

# 前置条件：Windows + Microsoft Excel + pywin32（pip install pywin32）。

# 用法示例：
# python evaluation_suite/dvsheet_create/export_chart_png.py \
#   --inputs evaluation_suite/results/codex \
#   --out-name chart.png \
#   --chart-index 1
# """

# from __future__ import annotations

# import argparse
# import sys
# import time
# from pathlib import Path
# from typing import Optional

# import win32com.client as win32
# import pythoncom


# def _ensure_repo_on_path():
#     root = Path(__file__).resolve().parents[2]
#     sys.path.append(str(root))


# _ensure_repo_on_path()


# def find_workbook(case_dir: Path) -> Optional[Path]:
#     for p in sorted(case_dir.iterdir()):
#         if p.is_file() and p.suffix.lower() in {".xlsx", ".xls"}:
#             return p
#     return None


# def export_chart_via_shape(excel, ws, chart_obj, out_path: Path):
#     """
#     将图表复制为图片，粘贴到工作表作为形状，再用形状.Export 输出 PNG。
#     这样由 Excel 完整渲染，刻度/图例不易丢失。
#     """
#     # 激活工作表与图表
#     ws.Activate()
#     try:
#         chart_obj.Activate()
#     except Exception:
#         pass
#     chart = chart_obj.Chart

#     # 尽量提高标签可见性
#     try:
#         # xlCategory=1, xlValue=2
#         cat = chart.Axes(1)
#         if hasattr(cat, "TickLabelSpacing"):
#             cat.TickLabelSpacing = 1
#         val = chart.Axes(2)
#         if hasattr(val, "TickLabelSpacing"):
#             val.TickLabelSpacing = 1
#     except Exception:
#         pass

#     # 复制为位图
#     chart.CopyPicture(Appearance=1, Format=2)  # xlScreen=1, xlBitmap=2
#     time.sleep(0.2)

#     # 粘贴并拿到刚粘贴的形状
#     ws.Paste()
#     time.sleep(0.2)
#     shape = ws.Shapes(ws.Shapes.Count)

#     # 临时放大，避免 Excel 隐藏标签
#     orig_w, orig_h = shape.Width, shape.Height
#     try:
#         shape.Width = max(orig_w, 900)
#         shape.Height = max(orig_h, 500)
#         time.sleep(0.2)
#     except Exception:
#         pass

#     # 导出形状为 PNG
#     out_abs = str(out_path.resolve())
#     shape.Export(Filename=out_abs, FilterName="PNG")

#     # 清理
#     try:
#         shape.Delete()
#     except Exception:
#         pass
#     excel.CutCopyMode = False


# def export_chart_png(excel, ws, chart_obj, out_path: Path):
#     ws.Activate()
#     chart_obj.Activate()
#     chart = chart_obj.Chart

#     # 轴标签尽量全显 - 包括主轴和次轴
#     try:
#         # xlCategory=1, xlValue=2
#         # xlPrimary=1, xlSecondary=2
        
#         # 主横轴
#         try:
#             cat = chart.Axes(1, 1)  # (Type, AxisGroup)
#             if hasattr(cat, "TickLabelSpacing"):
#                 cat.TickLabelSpacing = 1
#         except Exception:
#             pass
        
#         # 主纵轴
#         try:
#             val = chart.Axes(2, 1)
#             if hasattr(val, "TickLabelSpacing"):
#                 val.TickLabelSpacing = 1
#         except Exception:
#             pass
        
#         # 次横轴（如果存在）
#         try:
#             if chart.HasAxis(1, 2):  # xlCategory, xlSecondary
#                 cat2 = chart.Axes(1, 2)
#                 if hasattr(cat2, "TickLabelSpacing"):
#                     cat2.TickLabelSpacing = 1
#         except Exception:
#             pass
        
#         # 次纵轴（如果存在）- 这是右侧轴
#         try:
#             if chart.HasAxis(2, 2):  # xlValue, xlSecondary
#                 val2 = chart.Axes(2, 2)
#                 if hasattr(val2, "TickLabelSpacing"):
#                     val2.TickLabelSpacing = 1
#                 # 确保次轴可见
#                 val2.AxisBetweenCategories = False
#         except Exception:
#             pass
            
#     except Exception as e:
#         print(f"  [warn] 设置坐标轴时出错: {e}")

#     # 放大图表再导出，减少隐藏刻度
#     ow, oh = chart_obj.Width, chart_obj.Height
#     try:
#         chart_obj.Width = max(ow, 900)
#         chart_obj.Height = max(oh, 500)
#         time.sleep(0.3)  # 增加等待时间让次轴渲染
#     except Exception:
#         pass

#     chart.Export(Filename=str(out_path.resolve()), FilterName="PNG")

#     try:
#         chart_obj.Width, chart_obj.Height = ow, oh
#     except Exception:
#         pass

# def export_charts_batch(cases, chart_index):
#     pythoncom.CoInitialize()
#     excel = win32.Dispatch("Excel.Application")
#     excel.Visible = True
#     excel.WindowState = -4143  # 正常窗口
#     excel.DisplayAlerts = False
#     excel.ScreenUpdating = True
#     try:
#         for workbook_path, out_path in cases:
#             wb = None
#             try:
#                 wb = excel.Workbooks.Open(str(workbook_path.resolve()))
#                 time.sleep(0.2)
#                 ws = next((sh for sh in wb.Worksheets if getattr(sh.ChartObjects(), "Count", 0) > 0), wb.ActiveSheet)
#                 ws.Activate()
#                 charts = ws.ChartObjects()
#                 if charts.Count < chart_index:
#                     raise IndexError(f"{ws.Name} 只有 {charts.Count} 个图表")
#                 chart_obj = charts.Item(chart_index)
#                 export_chart_png(excel, ws, chart_obj, out_path)
#                 print(f"[ok] {workbook_path.parent.name} -> {out_path.name}")
#             except Exception as exc:
#                 print(f"[fail] {workbook_path.parent.name}: {exc}")
#             finally:
#                 if wb:
#                     wb.Close(SaveChanges=False)
#                 time.sleep(0.1)
#     finally:
#         excel.Quit()
#         pythoncom.CoUninitialize()

# def main():
#     parser = argparse.ArgumentParser(description="批量导出 Excel 图表为 PNG（Windows COM）")
#     parser.add_argument("--inputs", required=True, type=Path, help="候选结果目录，子目录为 case")
#     parser.add_argument("--chart-index", type=int, default=1, help="导出第几个图表，1 基，默认 1")
#     parser.add_argument("--out-name", default="chart.png", help="导出文件名，保存在 case 目录下")
#     args = parser.parse_args()

#     cases = []
#     for case_dir in sorted(p for p in args.inputs.iterdir() if p.is_dir()):
#         wb_path = find_workbook(case_dir)
#         if not wb_path:
#             print(f"[skip] {case_dir} 未找到 Excel 文件")
#             continue
#         out_path = case_dir / args.out_name
#         cases.append((wb_path, out_path))

#     if cases:
#         export_charts_batch(cases, args.chart_index)


# if __name__ == "__main__":
#     main()






"""
批量导出 Excel 图表为 PNG，存放在对应任务目录下（Windows + Excel COM）。
导出结果尽量与 Excel 中显示的一致。

前置条件：Windows + Microsoft Excel + pywin32（pip install pywin32）。

用法示例：
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
    导出图表为 PNG，保持与 Excel 显示一致。
    """
    ws.Activate()
    time.sleep(0.1)
    
    try:
        chart_obj.Activate()
    except Exception:
        pass
    
    chart = chart_obj.Chart

    # 确保所有坐标轴可见（不改变刻度密度，保持 Excel 原样）
    try:
        # 主横轴
        try:
            cat = chart.Axes(1, 1)
            # 不设置 TickLabelSpacing，保持 Excel 自动计算的值
        except Exception:
            pass
        
        # 主纵轴
        try:
            val = chart.Axes(2, 1)
        except Exception:
            pass
        
        # 次横轴
        try:
            if chart.HasAxis(1, 2):
                cat2 = chart.Axes(1, 2)
        except Exception:
            pass
        
        # 次纵轴（右侧）
        try:
            if chart.HasAxis(2, 2):
                val2 = chart.Axes(2, 2)
        except Exception:
            pass
            
    except Exception as e:
        print(f"  [warn] 检查坐标轴时出错: {e}")

    # 关键：不改变尺寸，使用当前在 Excel 中显示的尺寸
    # 只需等待渲染完成
    time.sleep(0.2)

    # 使用原始尺寸导出
    out_abs = str(out_path.resolve())
    chart.Export(Filename=out_abs, FilterName="PNG")


def export_charts_batch(cases, chart_index):
    pythoncom.CoInitialize()
    excel = win32.Dispatch("Excel.Application")
    
    # 让 Excel 可见但最小化，确保完整渲染
    excel.Visible = True
    excel.WindowState = -4140  # xlMinimized
    excel.DisplayAlerts = False
    excel.ScreenUpdating = True  # 必须启用以触发渲染
    
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
                
                # 找到含图表的工作表
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
                    raise IndexError(f"{ws.Name} 只有 {charts.Count} 个图表，索引 {chart_index} 越界")
                
                chart_obj = charts.Item(chart_index)
                
                # 导出（保持原始尺寸）
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
    parser = argparse.ArgumentParser(description="批量导出 Excel 图表为 PNG（Windows COM）")
    parser.add_argument("--inputs", required=True, type=Path, help="候选结果目录，子目录为 case")
    parser.add_argument("--chart-index", type=int, default=1, help="导出第几个图表，1 基，默认 1")
    parser.add_argument("--out-name", default="chart.png", help="导出文件名，保存在 case 目录下")
    parser.add_argument("--overwrite", action="store_true", help="若存在同名 PNG，是否覆盖。默认不覆盖。")
    args = parser.parse_args()

    cases = []
    for case_dir in sorted(p for p in args.inputs.iterdir() if p.is_dir() and p.name.startswith("dvsheet-create")):
        wb_path = find_workbook(case_dir)
        if not wb_path:
            print(f"[skip] {case_dir} 未找到 Excel 文件")
            continue
        out_path = case_dir / args.out_name
        if (not args.overwrite) and out_path.exists():
            print(f"[skip] {case_dir} 已存在 {args.out_name}，未覆盖。")
            continue
        cases.append((wb_path, out_path))

    if cases:
        export_charts_batch(cases, args.chart_index)


if __name__ == "__main__":
    main()

