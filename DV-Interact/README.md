# DV-Interact 构造流程

## 1. 选取 nvbench2.0  中数据大的问题，图的类型要丰富，要有难度

## 2. mock 数据

## 3. 整理数据格式

## 4. 用户模拟器
生成 fact_source prompt:
```
# Role Definition
You are an expert **User Simulator Architect** for a Data Visualization benchmark.
Your task is to analyze a raw test case (Query + Data Schema + Execution Steps) and generate a **"Hidden Logic Script" (`fact_source`)** for the User Simulator.

# Input Data
You will be provided with:
1.  **NL Query:** The user's original natural language request.
2.  **Table Schema:** Column names, examples, and `unique_value_counts`.
3.  **Steps/Gold Answer:** The mechanical execution steps (which might contain statistical errors).

# Your Core Logic (CRITICAL)
You must act as a **Statistical Critic**. Do not blindly trust the `NL Query` or `Steps`.

**Step 1: Sanity Check (Detect the Trap)**
Analyze the requested Chart Type vs. Data Distribution.
-   **The Box Plot Trap:** Did the user ask for a Box Plot on a column with very few unique values (e.g., `< 5` or `0/1` binary)? -> *This is a statistical error.* The Simulator must correct this to a continuous variable (e.g., "Amount").
-   **The Scatter Plot Trap:** Did the user ask for a Scatter Plot on a categorical column? -> *Error.* Needs continuous axis.
-   **The Ambiguity Trap:** Did the user say "High values" without defining the threshold? -> *Ambiguity.*

**Step 2: Construct the "True Intent"**
If the original query is flawed (Trap), invent a **logical business intent** that fixes it.
-   *Example:* Query = "Box plot of Payment Status (0/1)".
-   *Fix:* Intent = "Box plot of **Total Amount**, grouped by Payment Status".

**Step 3: Define Reaction Rules**
Create specific rules for the Simulator:
-   If the Agent follows the "Bad Query" (Trap), the Simulator must **complain** (e.g., "The chart is flat").
-   If the Agent asks for clarification, the Simulator reveals the "True Intent".
-   If the Agent asks for column names, the Simulator **refuses**.

# Output Format
Generate ONLY the text content for the `fact_source` field. Use the strict template below.

---
### [True Intent]
[Describe what the user ACTUALLY wants. If the original query was statistically wrong, describe the corrected version here.]
- **Correct Y-Axis:** "[Column Name or Description]" ([Data Type]).
- **Correct X-Axis:** "[Column Name or Description]" ([Data Type]).
- **Why:** [Brief business reason, e.g., "To compare the range of debts"].

### [Trap & Reaction Rules]
Your initial instruction "[Insert Original Query]" is [wrong/ambiguous] because [explain the statistical flaw or missing detail].
1. **IF the Agent blindly follows instructions** [describe the bad outcome, e.g., plots binary data]:
   - **REACTION:** Complain. Say: "[Insert a natural language complaint, e.g., 'This looks flat!']"
2. **IF the Agent asks for clarification**:
   - **REACTION:** Correct yourself. Say: "[Insert the corrected intent, e.g., 'I meant plot the Amount.']"
3. **IF the Agent asks for column names**:
   - **REACTION:** Refuse. Say: "I don't know the technical column names. Just show me the [Business Term]."
---

# Now, process this input:
{ }
```
可以让它输出形式
```
[
    {
        "fact_source": "[content]"
    }
]
```

# 5. GT 生成

将上一个阶段给用户模拟器的配置（True Intent）、数据和问题给模型，不断润色模型的结果，也就是可视化的图

留住最终的图和代码

这个代码里面要自带绘图数据（而不是引用csv文件）
prompt：
```
# Role
你是一位世界级的数据可视化专家和 Python 编程大师。你的任务是为数据可视化评测基准生成“标准答案”（Ground Truth）。
你需要编写一段独立的、可直接执行的 Python 代码，绘制出完美的图表。

# Input Data
你将收到以下三个输入：
1.  **Original Query (原始问题):** 用户的自然语言请求（注意：这里可能包含统计学陷阱或模糊不清的描述）。
2.  **True Intent (真实意图):** 由用户模拟器分析出的正确绘图逻辑。**这是你必须遵循的唯一真理。**
3.  **Raw Data Snippet (原始数据):** 绘图所需的具体数据。

# Critical Constraints (必须严格遵守)

## 1. 数据自包含 (Self-Contained Data) - 核心要求！
* **严禁**使用 `pd.read_csv()`、`open()` 或任何加载外部文件的操作。
* **必须**将绘图所需的数据直接硬编码在 Python 脚本中。
    * 使用 `pd.DataFrame({...})` 或字典/列表的形式定义数据。
    * *注意：如果原始数据量很大，请在代码中仅包含经过筛选或聚合后、绘图真正需要的那些数据点，以保持代码简洁。*

## 2. 逻辑准确性 (Logic Fidelity)
* **忽略** `Original Query` 中的错误逻辑（例如：如果用户要求对分类变量画散点图，请忽略该要求）。
* **严格执行** `True Intent` 中定义的逻辑（包括正确的 X/Y 轴选择、聚合方式、图表类型）。

## 3. 视觉美观度 (Aesthetics)
* 使用专业风格（推荐 `seaborn` 或 `matplotlib` 的美化配置）。
* **避免遮挡**：确保标签（Title, Axis Labels, Ticks, Legend）清晰可读，不重叠。如果 X 轴标签过长，请进行旋转或换行处理。
* **标题与标注**：添加描述性的标题和带有单位的轴标签。
* **配色**：使用区分度高的配色方案。

# Input Context
---
**Original Query:**
{original_query}

**True Intent (Source of Truth):**
{true_intent_from_step_4}

**Raw Data Content:**
{raw_data_content}
---

# Output Requirement
请仅输出 **Python 代码块**。代码必须能够直接复制运行并显示图像（使用 `plt.show()`）。不要输出任何解释性文字。
```

# 6. rubric 生成

包含维度：
    1. **交互评估 (Dimension 1):** 检查【轨迹数据】中的对话记录。

    2. **逻辑评估 (Dimension 2):** 检查【轨迹数据】中助手生成的**最后一段 Python 代码**。

    3. **展示评估 (Dimension 3):** 检查【可视化图】的效果是否符合要求。


将最终的图和代码，问题，fact_source 给模型生成rubric，不断润色

prompt：
```
# Role
You are the **Lead Auditor** for the DVWorld Benchmark. Your task is to generate a **Strict, Quantitative, and Evidence-Based Scoring Rubric**.
You do NOT grade the agent yet. You only define the **Rules of Law** based on the provided `Fact Source` and `User Instruction`.

# Core Philosophy: "Code is Law"
Unlike general evaluation, this rubric must be **executable** and **falsifiable**.
- **Avoid Vague Adjectives:** Do NOT write "Did the agent clean the data well?"
- **Use Hard Constraints:** MUST write "Did the code filter `status == 'Active'`?" or "Did the code exclude values `< 0`?"
- **Numerical Precision:** Any number mentioned in the `Fact Source` (e.g., threshold 50%, year 2023) MUST appear explicitly in the rubric.

# Input Data
1. **User Instruction:** The natural language query.
2. **Fact Source:** The ground truth logic (Business rules, formulas, thresholds).
3. The python script (used to verify implementation details).
4. The final chart (used to verify visual labels).

# Rubric Construction Guide
For each dimension, you must extract **Hard Rules** from the input:

## Dimension 1: Data Logic & Factuality (The Hardest Constraints)
*Source: Fact Source + Agent Code*
- **Formulas:** If Fact Source says `Profit = Rev - Cost`, the rubric must check for exactly this operation.
- **Filters:** If Fact Source says "Exclude Q1", the rubric must check if the code filters out Jan/Feb/Mar or Q1.
- **Thresholds:** If Fact Source says "High Value is > 1000", the rubric must check for `> 1000`.

## Dimension 2: Visual Semantics
*Source: User Instruction + Agent Image*
- **Mapping:** Did the agent map the correct column to the correct axis?
- **Chart Type:** Is it strictly the requested type?

# Output Format
**[Total Score | {N} points] Strict Evaluation Rubric**

## 1. Data Integrity & Business Logic (Strict Checks)
- **1.1[1 pt] Value Threshold Enforcement:** The code MUST explicitly filter data using the condition `{Insert Condition, e.g., df['amount'] > 5000}`.
- **1.2[1 pt] Formula Accuracy:** The calculated metric MUST use the formula `{Insert Formula}` as defined in Fact Source.
- **1.3[1 pt] Exclusion Logic:** The code MUST exclude rows where `{Column} == {Value}`.

## 2. Visualization Semantics
- **2.1[1 pt] Axis Mapping:** The Y-axis MUST display `{Column Name}`.
- **2.2[1 pt] Grouping Granularity:** The X-axis MUST be grouped by `{Time/Category}`.

*(End of output. Do not provide evaluation results.)*


## input

User Instruction：

Fact Source：

python script：

```