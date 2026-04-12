# DVSheet-Dashboards 评估（Windows + Excel + Rubric + LLM）

该任务类型使用 **Rubric + 多模态 LLM** 评估，并会先把仪表盘工作表中的图表 **逐个导出为 PNG**，再把多张图片一起作为模型输入。

此外，会通过 Excel COM 提取仪表盘中的：
- 表格预览（UsedRange 的前 N 行/列，转为 markdown）
- 图表列表与系列（系列公式 + X/Y 样本点）
并放入 prompt 的 `{chart_data}`，辅助 rubric 对 KPI 数值/图例/趋势等做更精确的打分。
注意：表格/图表数据提取只用于 `{chart_data}` 文本补充信息；图像部分采用“逐个图表导出”，不是整张 sheet 截图。

## 依赖

`evaluation_suite/requirements.txt`：
- `openai`
- `xlwings`
- `pywin32`（Windows）

## 目录约定

- 候选结果：`<inputs>/<case_id>/*.xlsx`
- gold：`evaluation_suite/gold/<case_id>/query.md`、`rubric.md`、`metadata.json`
- 仅评估 `case_id` 以 `dvsheet-dashboards` 开头的任务。

## 运行（Windows）

```bash
python evaluation_suite/dvsheet_dashboards/run_eval.py --inputs evaluation_suite/results/gemini-3-pro-preview-new-dashboards-test1 --gold-dir evaluation_suite/gold --out-dir evaluation_suite/model_score --model gemini-2.5-flash
```

输出：`evaluation_suite/model_score/<inputs_name>/dvsheet-dashboards-results.json`

如果需要指定导出工作表名：
```bash
python evaluation_suite/dvsheet_dashboards/run_eval.py --inputs <...> --sheet Dashboard
```

如果遇到 `RPC` 报错或导出空白/不完整，建议用调试模式运行以便看 Excel 是否被弹窗/受保护视图阻塞：
```bash
python evaluation_suite/dvsheet_dashboards/run_eval.py --inputs <...> --visible
```

仅导出图表 PNG（不做 LLM 评分）可用：
```bash
python evaluation_suite/dvsheet_dashboards/export_dashboard_png.py --inputs <...>
```

导出实现参考 `evaluation_suite/dvsheet_create/export_chart_png.py`：遍历 `ChartObjects()`，对每个图表调用 `Chart.Export`。

## 拼接为“整张仪表盘”

由于当前导出的是“逐个图表 PNG”，你可以在导出后把这些图按 Excel 中的位置拼成一张大图（不依赖 Excel）：

```bash
python evaluation_suite/dvsheet_dashboards/stitch_dashboard_png.py --case-dir evaluation_suite/results/codex/dvsheet-dashboards-001
```

如果你希望拼接结果里也包含表格与标题（但不需要背景/格式），可以渲染“文本层”（需要 `dashboard_layout.json`，导出图表时会自动生成）：

```bash
python evaluation_suite/dvsheet_dashboards/stitch_dashboard_png.py --case-dir evaluation_suite/results/codex/dvsheet-dashboards-001 --with-text
```

如果文本太小，可调大字号缩放：
```bash
python evaluation_suite/dvsheet_dashboards/stitch_dashboard_png.py --case-dir evaluation_suite/results/codex/dvsheet-dashboards-001 --with-text --font-scale 1.5
```

评测脚本默认会生成 `dashboard_stitched.png`（表格/标题 + 背景填充 + 图表覆盖）并优先用它进行 LLM 评估；如果拼接失败则回退到逐个图表 PNG。
