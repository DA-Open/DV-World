# DVSheet-Fix 评估（Windows + Office + xlwings）

DVSheet-Fix 的 **Candidate** 与 **Gold Standard** 都是 Excel 文件；评估在 Windows + Microsoft Excel 环境下，通过 `xlwings` 调用 Excel COM 读取图表对象，比较：
- 图表类型（折线/柱状/饼图等）
- 系列绑定（categories / values 对应的数据序列）
- 坐标轴范围是否为自动/手动（用于轴刻度修复类任务）

## 依赖

`evaluation_suite/requirements.txt`：
- `xlwings`
- `pywin32`（Windows）

## 目录约定

- 候选结果：`<inputs>/<case_id>/*.xlsx`
- 正确答案：`evaluation_suite/gold/<case_id>/*.xlsx`
- 仅评估 `case_id` 以 `dvsheet-fix` 开头的任务。

## 运行

```bash
python evaluation_suite/dvsheet_fix/run_eval.py --inputs /Users/bytedance/Documents/DVSheet/evaluation_suite/results/gemini-3-pro-preview-new-create-test1 --gold-dir evaluation_suite/gold --out-dir evaluation_suite/model_score
```

输出：`evaluation_suite/model_score/<inputs_name>/dvsheet-fix-results.json`

## 使用 Broken 做 0/1 判定（推荐）

如果你有每个 case 的初始待修复文件（Broken），评估器会先比较 `Broken vs Gold` 自动推导“必须修复的关键属性（must-fix）”，然后对 Candidate 做硬门槛判定：**全部修到则 1，否则 0**。

### 方式 A：Broken 与 Gold 放在同一个 gold 目录（文件名含 start）

约定：`evaluation_suite/gold/<case_id>/` 下同时存在：
- `*start*.xlsx`：Broken（初始待修复文件）
- 另一个 `*.xlsx`：Gold（正确答案文件）

运行：
```bash
python evaluation_suite/dvsheet_fix/run_eval.py --inputs evaluation_suite/results/codex --gold-dir evaluation_suite/gold --out-dir evaluation_suite/model_score
```

### 方式 B：单独提供 broken-dir

```bash
python evaluation_suite/dvsheet_fix/run_eval.py --inputs evaluation_suite/results/codex --broken-dir evaluation_suite/broken --gold-dir evaluation_suite/gold --out-dir evaluation_suite/model_score
```

约定：`evaluation_suite/broken/<case_id>/*.xlsx`

调试模式（显示 Excel 窗口）：
```bash
python evaluation_suite/dvsheet_fix/run_eval.py --inputs <...> --visible
```
