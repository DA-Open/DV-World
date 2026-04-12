python evaluation_suite/dvsheet_create/run_eval.py  --inputs evaluation_suite/results/gemini-3-pro-preview-new-create-test1 --model gemini-2.5-flash
 
 python evaluation_suite/dvsheet_create/export_chart_png.py --inputs evaluation_suite\results\gemini-3-pro-preview-new-create-test1 --chart-index 1 --out-name chart.png



  - run_eval.py 新增参数：
      - --combine-mode {product,weighted}（默认 product）
      - --vis-weight, --table-weight（仅 weighted 模式使用）
  - 打印示例：
    [dvsheet-create-001] score=88.000% (Fidelity=100.000%, Logic=60.000%, Aesthetics=100.000%, table=100.000%, rubric=86.000%)
    会包含各维度、表格覆盖率和 rubric 总分（vlm_total_norm）。
  - 结果 JSON 现在记录 table_score/percent、rubric 分、gold workbook 路径、组合模式和权重。

  如需调整为加权模式，运行示例：
  python evaluation_suite/dvsheet_create/run_eval.py --inputs ... --combine-mode weighted --vis-weight 0.6 --table-weight 0.4
