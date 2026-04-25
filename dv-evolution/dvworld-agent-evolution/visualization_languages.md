# Visualization Languages Overview

This document introduces five visualization languages (Python, ECharts, Vega-Lite, D3.js, Plotly.js), explains their typical usage, and provides a minimal example for each.

## 1) Python (Matplotlib)

**What it is**
Python is a general-purpose programming language widely used for data analysis and visualization. Matplotlib is the most common plotting library in Python, offering full control over static charts.

**Typical strengths**
- Full programmatic control for data processing and chart styling.
- Strong ecosystem for analysis (pandas, numpy, scipy).
- Good for batch-generated reports and static figures.

**Example (save PNG)**
```python
import matplotlib.pyplot as plt

categories = ["A", "B", "C"]
values = [12, 18, 9]

plt.figure(figsize=(5, 3))
plt.bar(categories, values, color="#4C78A8")
plt.title("Sample Bar Chart")
plt.xlabel("Category")
plt.ylabel("Value")
plt.tight_layout()
plt.savefig("result.png")
```

## 2) Apache ECharts

**What it is**
ECharts is a JavaScript charting library that renders interactive charts in the browser using Canvas or SVG. Charts are defined with a JSON-style "option" object.

**Typical strengths**
- High-quality interactive charts with rich configuration.
- Easy to integrate in web apps.
- Flexible styling and animation.

**Example (option JSON)**
```json
{
  "title": { "text": "Sample Bar Chart" },
  "tooltip": {},
  "xAxis": { "type": "category", "data": ["A", "B", "C"] },
  "yAxis": { "type": "value" },
  "series": [
    { "type": "bar", "data": [12, 18, 9], "itemStyle": { "color": "#4C78A8" } }
  ]
}
```

## 3) Vega-Lite

**What it is**
Vega-Lite is a high-level declarative grammar for interactive charts, expressed as JSON. It compiles to a lower-level Vega spec.

**Typical strengths**
- Concise, declarative specifications.
- Fast to iterate and easy to generate programmatically.
- Good for dashboards and data-driven UIs.

**Example (spec JSON)**
```json
{
  "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
  "data": {
    "values": [
      { "category": "A", "value": 12 },
      { "category": "B", "value": 18 },
      { "category": "C", "value": 9 }
    ]
  },
  "mark": { "type": "bar", "color": "#4C78A8" },
  "encoding": {
    "x": { "field": "category", "type": "nominal" },
    "y": { "field": "value", "type": "quantitative" }
  },
  "title": "Sample Bar Chart"
}
```

## 4) D3.js

**What it is**
D3.js is a low-level JavaScript library for visualizing data by manipulating the DOM (SVG/Canvas). It provides maximum control for custom visualizations.

**Typical strengths**
- Fully custom designs and interactions.
- Powerful for bespoke visual storytelling.
- Large community and plugin ecosystem.

**Example (minimal SVG bar chart)**
```js
const data = [
  { category: "A", value: 12 },
  { category: "B", value: 18 },
  { category: "C", value: 9 }
];

const width = 300;
const height = 180;
const margin = { top: 20, right: 10, bottom: 30, left: 30 };

const x = d3.scaleBand()
  .domain(data.map(d => d.category))
  .range([margin.left, width - margin.right])
  .padding(0.2);

const y = d3.scaleLinear()
  .domain([0, d3.max(data, d => d.value)])
  .nice()
  .range([height - margin.bottom, margin.top]);

const svg = d3.select("body").append("svg")
  .attr("width", width)
  .attr("height", height);

svg.append("g")
  .selectAll("rect")
  .data(data)
  .join("rect")
  .attr("x", d => x(d.category))
  .attr("y", d => y(d.value))
  .attr("height", d => y(0) - y(d.value))
  .attr("width", x.bandwidth())
  .attr("fill", "#4C78A8");

svg.append("g")
  .attr("transform", `translate(0,${height - margin.bottom})`)
  .call(d3.axisBottom(x));

svg.append("g")
  .attr("transform", `translate(${margin.left},0)`)
  .call(d3.axisLeft(y));
```

## 5) Plotly.js

**What it is**
Plotly.js is a high-level JavaScript charting library built on top of D3 and WebGL, focused on interactive charts and dashboards.

**Typical strengths**
- Interactive charts with minimal configuration.
- Wide chart type support.
- Great for rapid prototyping in web apps.

**Example (bar chart)**
```js
const trace = {
  x: ["A", "B", "C"],
  y: [12, 18, 9],
  type: "bar",
  marker: { color: "#4C78A8" }
};

const layout = {
  title: "Sample Bar Chart",
  xaxis: { title: "Category" },
  yaxis: { title: "Value" }
};

Plotly.newPlot("chart", [trace], layout);
```
