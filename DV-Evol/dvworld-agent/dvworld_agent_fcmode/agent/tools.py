import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from dvworld_agent_fcmode.agent.action import (
    Action,
    Bash,
    Python,
    LOCAL_DB_SQL,
    Terminate,
    RenderChart,
)


def _parse_arguments(raw_args: Any) -> Dict[str, Any]:
    if raw_args is None:
        return {}
    if isinstance(raw_args, dict):
        return raw_args
    if isinstance(raw_args, str):
        candidates = [
            raw_args,
            raw_args.replace("\n", "\\n"),
            raw_args.replace("'", '"'),
            raw_args.replace("\n", "\\n").replace("'", '"'),
        ]
        for candidate in candidates:
            try:
                return json.loads(candidate)
            except Exception:
                pass

        parsed: Dict[str, Any] = {}
        file_match = re.search(
            r'(file_path|filepath|image_path)\s*[:=]\s*["\']([^"\']+)["\']',
            raw_args,
            flags=re.IGNORECASE,
        )
        if file_match:
            parsed_key = file_match.group(1).lower()
            value = file_match.group(2)
            if parsed_key == "filepath":
                parsed["filepath"] = value
            elif parsed_key == "image_path":
                parsed["image_path"] = value
            else:
                parsed["file_path"] = value

        output_match = re.search(r'output\s*[:=]\s*["\']([^"\']+)["\']', raw_args, flags=re.IGNORECASE)
        if output_match:
            parsed["output"] = output_match.group(1)

        report_match = re.search(r'report_path\s*[:=]\s*["\']([^"\']+)["\']', raw_args, flags=re.IGNORECASE)
        if report_match:
            parsed["report_path"] = report_match.group(1)

        content_match = re.search(r'content\s*[:=]\s*([\'"])', raw_args, flags=re.IGNORECASE)
        if content_match:
            quote = content_match.group(1)
            start = content_match.end()
            tail = raw_args[start:]
            end = tail.rfind(quote)
            if end > 0:
                parsed["content"] = tail[:end]
            else:
                parsed["content"] = tail

        command = None
        for key in ("command", "sql"):
            key_match = re.search(rf"{key}\s*[:=]\s*(['\"])", raw_args, flags=re.IGNORECASE | re.DOTALL)
            if not key_match:
                continue
            quote = key_match.group(1)
            start = key_match.end()
            tail = raw_args[start:]
            output_idx = re.search(r"\boutput\s*[:=]", tail, flags=re.IGNORECASE)
            if output_idx:
                tail = tail[: output_idx.start()]
            if quote in tail:
                end = tail.rfind(quote)
                if end > 0:
                    command = tail[:end]
            if command is None:
                command = tail
            if command is not None:
                command = command.strip().rstrip(",").rstrip("}")
                break
        if "code" not in parsed:
            code_match = re.search(r'code\s*[:=]\s*([\'"])', raw_args, flags=re.IGNORECASE | re.DOTALL)
            if code_match:
                quote = code_match.group(1)
                start = code_match.end()
                tail = raw_args[start:]
                if quote in tail:
                    end = tail.rfind(quote)
                    parsed["code"] = tail[:end].strip()
                else:
                    parsed["code"] = tail.strip()

        if command:
            parsed["command"] = command.strip()
        if "filepath" not in parsed and "file_path" in parsed:
            parsed["filepath"] = parsed["file_path"]
        if "file_path" not in parsed and "filepath" in parsed:
            parsed["file_path"] = parsed["filepath"]
        if "file_path" not in parsed and "image_path" in parsed:
            parsed["file_path"] = parsed["image_path"]
        return parsed
    return {}


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: Dict[str, Any]

    def to_openai(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class SpiderToolset:
    def __init__(self, language: str = "en", task_id: str = "", viz_lang: str = "python"):
        self.language = (language or "en").lower()
        self.viz_lang = (viz_lang or "python").lower()
        task_prefix = (task_id or "").strip().lower()
        self._tools: List[ToolDefinition] = [
            ToolDefinition(
                name="bash",
                description=(
                    "Run a non-interactive shell command from the workspace root. "
                    "Use this to inspect files or run scripts for analysis. "
                    "It can be used to create and run Python files or other scripts (python3 recommended)."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Shell command to run from the workspace root.",
                        }
                    },
                    "required": ["code"],
                },
            ),
            ToolDefinition(
                name="python",
                description=(
                    "Write Python code to a file (default temp.py) and execute it with python3 from the workspace root. "
                    "Use for data analysis, plotting, and generating markdown/CSV outputs."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Optional file path to write and run (default temp.py).",
                        },
                        "code": {
                            "type": "string",
                            "description": "Python code to run.",
                        },
                    },
                    "required": ["code"],
                },
            ),
            ToolDefinition(
                name="local_db_sql",
                description=(
                    "Run read-only SQL (SELECT/WITH/PRAGMA) against a local SQLite or DuckDB file to explore data and compute results. "
                    "By default results are printed directly; if an output_result_path is provided, results are "
                    "saved to CSV. Observations are truncated to the first 5000 characters."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Database file path (e.g., dacomp-XXX.sqlite).",
                        },
                        "command": {"type": "string", "description": "SQL command to execute."},
                        "output_result_path": {
                            "type": "string",
                            "description": (
                                "Optional CSV path to save the full result. If omitted, results are printed directly."
                            ),
                        },
                        "output": {
                            "type": "string",
                            "description": "Deprecated alias for output_result_path.",
                        },
                    },
                    "required": ["file_path", "command"],
                },
            ),
            ToolDefinition(
                name="finish",
                description=(
                    "Terminate the session. Do not write reports. Provide an optional brief message if needed."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "Optional short completion message.",
                        },
                    },
                    "required": [],
                },
            ),
        ]
        # Optional tools by task type
        if task_prefix.startswith("dv-evol"):
            self._tools.append(
                ToolDefinition(
                    name="load_image",
                    description=(
                        "Read an image file (png/jpg) from the workspace and return it as a base64 data URI so the model can view it."
                    ),
                    parameters={
                        "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to the image file (absolute or relative to workspace).",
                        }
                    },
                    "required": ["file_path"],
                },
                )
            )
            if self.viz_lang != "python":
                self._tools.append(
                    ToolDefinition(
                        name="render_chart",
                        description=(
                            "Render a visualization spec/snippet (echarts, vega-lite, d3.js, plotly.js) "
                            "to a PNG image using Playwright. Use after writing result.json/result.js."
                        ),
                        parameters={
                            "type": "object",
                            "properties": {
                                "file_path": {
                                    "type": "string",
                                    "description": "Path to the spec/snippet to render (e.g., result.json or result.js).",
                                },
                                "tool_type": {
                                    "type": "string",
                                    "description": "Visualization library to render.",
                                    "enum": ["echarts", "vega-lite", "d3.js", "plotly.js", "plotly"],
                                },
                                "output_path": {
                                    "type": "string",
                                    "description": "PNG output path (default result.png).",
                                },
                            },
                            "required": ["file_path"],
                        },
                    )
                )

    def build_tools_param(self) -> List[Dict[str, Any]]:
        return [tool.to_openai() for tool in self._tools]

    def get_instructions(self) -> str:
        lines = [
            "Use the following tools via function calls (Qwen XML / OpenAI tool calling is supported).",
            "Call `finish` to write the markdown report and terminate.",
        ]
        for tool in self._tools:
            lines.append(f"- {tool.name}: {tool.description}")
        return "\n".join(lines)

    def to_action(self, tool_call: Dict[str, Any]) -> Optional[Action]:
        function = tool_call.get("function") or {}
        name = (function.get("name") or "").lower()
        arguments = _parse_arguments(function.get("arguments"))
        if name == "bash":
            code = arguments.get("code")
            if not code:
                return None
            return Bash(code=str(code))

        if name == "python":
            code = arguments.get("code")
            file_path = arguments.get("file_path") or arguments.get("filepath") or "temp.py"
            if not code:
                return None
            return Python(code=str(code), filepath=str(file_path))

        if name == "render_chart":
            file_path = arguments.get("file_path") or arguments.get("filepath")
            if not file_path:
                return None
            tool_type = arguments.get("tool_type") or self.viz_lang
            output_path = arguments.get("output_path") or "result.png"
            return RenderChart(
                file_path=str(file_path),
                tool_type=str(tool_type),
                output_path=str(output_path),
            )

        if name == "local_db_sql":
            file_path = arguments.get("file_path")
            command = arguments.get("command")
            output = arguments.get("output_result_path") or arguments.get("output") or "direct"
            if not file_path or not command:
                return None
            return LOCAL_DB_SQL(file_path=str(file_path), code=str(command), output=str(output))

        if name == "finish":
            content = arguments.get("content") or arguments.get("output")
            image_path = arguments.get("report_path") or arguments.get("filepath") or "figure.png"
            return Terminate(report_path=str(image_path), content=str(content) if content is not None else None)

        if name == "load_image":
            file_path = arguments.get("file_path") or arguments.get("filepath") or arguments.get("image_path")
            if not file_path:
                return None
            from dvworld_agent_fcmode.agent.action import LoadImage  # local import to avoid cycle

            return LoadImage(file_path=str(file_path))

        return None
