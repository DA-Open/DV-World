import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dvworld_agent_fcmode.agent.prompts import (
    DV_EVOL_PROMPT,
)
from dvworld_agent_fcmode.agent.action import Action, Terminate, Bash, Python, LOCAL_DB_SQL, LoadImage
from dvworld_agent_fcmode.agent.models import call_llm
from dvworld_agent_fcmode.agent.tools import SpiderToolset
from dvworld_agent_fcmode.envs.spider_agent import Spider_Agent_Env
from dvworld_agent_fcmode.envs.utils import calculate_sha256
from dvworld_agent_fcmode.agent.prompts import DV_SHEET_CREATE_PROMPT, DV_SHEET_FIX_PROMPT, DV_SHEET_DASHBOARDS_PROMPT

logger = logging.getLogger("dvworld_agent_fcmode")


class DVWorldAgent:
    def __init__(
        self,
        model: str = "gpt-4o",
        max_tokens: int = 1500,
        top_p: float = 0.9,
        temperature: float = 0.5,
        max_memory_length: int = 60,
        max_steps: int = 60,
        use_plan: bool = False,
        use_image_prompt: bool = False,
        language: str = "zh",
        viz_lang: str = "python",
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.top_p = top_p
        self.temperature = temperature
        self.max_memory_length = max_memory_length
        self.max_steps = max_steps
        self.use_plan = use_plan
        self.use_image_prompt = use_image_prompt
        self.language = (language or "zh").lower()
        self.viz_lang = (viz_lang or "python").lower()
        self.use_seed_prompt = False

        self.thoughts: List[str] = []
        self.responses: List[Any] = []
        self.actions: List[Action] = []
        self.observations: List[str] = []
        self.system_message = ""
        self.history_messages: List[Dict[str, Any]] = []
        self.env: Optional[Spider_Agent_Env] = None
        self.work_dir = "/workspace"
        self.toolset = SpiderToolset(language=self.language, viz_lang=self.viz_lang)
        self._last_observation = "You are in the folder now."
        self._saw_data_probe = False
        self._sql_calls = 0
        self._bash_calls = 0
        self._last_db_path: Optional[str] = None
        self._invalid_tool_call_streak = 0
        self._max_invalid_tool_call_retries = 10
        self._long_run_trim_after = 90
        self._long_run_keep_steps = min(self.max_memory_length, 60)
        self._pin_first_user_step = True
        self._repeat_action_streak = 0
        self._repeat_action_limit = 5
        self._last_action_repr: Optional[str] = None
        self._db_missing_streak = 0
        self._llm_failure_streak = 0
        self._max_llm_failure_retries = int(os.getenv("MAX_LLM_FAILURE_RETRIES", "5"))
        self._image_cache: List[str] = []

    def _render_action_space(self) -> str:
        """Return a concise action space listing for the system prompt."""
        lines = []
        for tool in self.toolset._tools:
            lines.append(f"- {tool.name}: {tool.description}")
        return "\n".join(lines)

    def set_env_and_task(self, env: Spider_Agent_Env):
        self.env = env
        self.thoughts.clear()
        self.responses.clear()
        self.actions.clear()
        self.observations.clear()
        self.history_messages.clear()
        self.instruction = self.env.task_config["instruction"]
        task_id = getattr(self.env, "task_id", "") if self.env else ""
        self.toolset = SpiderToolset(language=self.language, task_id=task_id, viz_lang=self.viz_lang)
        tool_instructions = self._render_action_space()
        self._saw_data_probe = False
        self._sql_calls = 0
        self._bash_calls = 0
        self._saw_data_probe = False
        self._last_db_path = self._guess_db_path()
        self._invalid_tool_call_streak = 0
        self._repeat_action_streak = 0
        self._last_action_repr = None
        self._db_missing_streak = 0
        self._image_cache = []
        self._last_observation = "You are in the folder now."

        self.system_message = self._select_prompt(tool_instructions)

        self.history_messages.append({"role": "system", "content": self.system_message})

    def _select_prompt(self, tool_instructions: str) -> str:
        task_id = getattr(self.env, "task_id", "") if self.env else ""
        if task_id.startswith("dvsheet-create"):
            return DV_SHEET_CREATE_PROMPT.format(
                work_dir=self.work_dir,
                max_steps=self.max_steps,
                task=self.instruction,
            )
        if task_id.startswith("dvsheet-fix"):
            return DV_SHEET_FIX_PROMPT.format(
                work_dir=self.work_dir,
                max_steps=self.max_steps,
                task=self.instruction,
            )
        if task_id.startswith("dvsheet-dashboards"):
            return DV_SHEET_DASHBOARDS_PROMPT.format(
                work_dir=self.work_dir,
                max_steps=self.max_steps,
                task=self.instruction,
            )
        if task_id.startswith("dv-evol"):
            prompt = DV_EVOL_PROMPT.get(self.viz_lang, DV_EVOL_PROMPT["python"])
            return prompt.format(
                work_dir=self.work_dir,
                max_steps=self.max_steps,
                viz_lang=self.viz_lang,
                task=self.instruction,
            )
        return DV_SHEET_CREATE_PROMPT.format(
            work_dir=self.work_dir,
            max_steps=self.max_steps,
            task=self.instruction,
        )

    def _normalize_content(self, content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                part.get("text", "") if isinstance(part, dict) else str(part) for part in content
            )
        return str(content)

    def _normalize_tool_calls(self, tool_calls: Any) -> List[Dict[str, Any]]:
        if not tool_calls:
            return []
        if not isinstance(tool_calls, list):
            return []
        normalized: List[Dict[str, Any]] = []
        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                continue
            call = dict(tool_call)
            call.setdefault("type", "function")
            function = call.get("function") or {}
            if not isinstance(function, dict):
                function = {"name": str(function), "arguments": "{}"}
            else:
                function = dict(function)
                if "name" not in function:
                    function["name"] = ""
                arguments = function.get("arguments")
                if arguments is None:
                    arguments = "{}"
                elif isinstance(arguments, dict):
                    arguments = json.dumps(arguments, ensure_ascii=False)
                elif not isinstance(arguments, str):
                    arguments = json.dumps(arguments, ensure_ascii=False)
                function["arguments"] = arguments
            call["function"] = function
            normalized.append(call)
        return normalized

    def _guess_db_path(self) -> Optional[str]:
        if not self.env:
            return None
        root = Path(getattr(self.env, "mnt_dir", "") or "")
        if not root or not root.exists():
            return None
        for pattern in ("*.sqlite", "*.db", "*.duckdb"):
            for path in root.rglob(pattern):
                try:
                    return path.relative_to(root).as_posix()
                except ValueError:
                    return path.as_posix()
        return None

    def _find_markdown_outputs(self) -> List[str]:
        if not self.env:
            return []
        root = Path(getattr(self.env, "mnt_dir", "") or "")
        if not root or not root.exists():
            return []
        init_hashes = getattr(self.env, "init_files_hash", {}) or {}
        results: List[str] = []
        for path in root.rglob("*.md"):
            if not path.is_file():
                continue
            path_str = path.as_posix()
            if path_str in init_hashes:
                try:
                    if calculate_sha256(path_str) == init_hashes[path_str]:
                        continue
                except Exception:
                    pass
            try:
                results.append(str(path.relative_to(root)))
            except ValueError:
                results.append(path_str)
            if len(results) >= 5:
                break
        return results

    def _update_last_db_path(self, text: str) -> None:
        if not text:
            return
        matches = re.findall(r"([\\w./-]+\\.(?:sqlite|db|duckdb))", text, flags=re.IGNORECASE)
        if not matches:
            return
        candidate = matches[0].lstrip("./")
        self._last_db_path = candidate

    def _extract_code_block(self, text: str) -> Optional[str]:
        if not text:
            return None
        fenced = re.search(r"```(?:[a-zA-Z0-9_+-]+)?\\n(.*?)```", text, flags=re.DOTALL)
        if fenced:
            return fenced.group(1).strip()
        inline_blocks = re.findall(r"`([^`]+)`", text, flags=re.DOTALL)
        if inline_blocks:
            return inline_blocks[-1].strip()
        return None

    def _fallback_tool_calls(self, content: str) -> List[Dict[str, Any]]:
        if not content:
            return []
        match = re.search(r"Action:\\s*([A-Za-z_]+)", content)
        if not match:
            return []
        action = match.group(1).strip().lower()
        command = self._extract_code_block(content)
        if not command:
            lines = content.splitlines()
            for idx, line in enumerate(lines):
                if line.lower().startswith("action:"):
                    trailing = []
                    for next_line in lines[idx + 1:]:
                        lower = next_line.strip().lower()
                        if lower.startswith(("response", "observation", "action:", "assistant:", "user:")):
                            break
                        trailing.append(next_line)
                    command = "\n".join(trailing).strip()
                    break
        if action == "bash" and command:
            args = {"code": command}
        elif action == "local_db_sql" and command:
            db_path = self._last_db_path or self._guess_db_path()
            if not db_path:
                return []
            args = {"file_path": db_path, "command": command}
        elif action == "python" and command:
            file_path = None
            file_match = re.search(r"(file_path|filepath)\s*[:=]\s*([\\w./-]+)", content, flags=re.IGNORECASE)
            if file_match:
                file_path = file_match.group(2)
            args = {"code": command}
            if file_path:
                args["file_path"] = file_path
        else:
            return []
        return [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": action, "arguments": json.dumps(args)},
            }
        ]

    def _split_history_prefix(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        if not self.history_messages:
            return [], []
        idx = 0
        while idx < len(self.history_messages) and self.history_messages[idx].get("role") == "system":
            idx += 1
        prefix = list(self.history_messages[:idx])
        if not self._pin_first_user_step or idx >= len(self.history_messages):
            return prefix, self.history_messages[idx:]
        if self.history_messages[idx].get("role") != "user":
            return prefix, self.history_messages[idx:]
        # Pin the first user step (user + following assistant/tool messages) to keep the task context.
        prefix.append(self.history_messages[idx])
        idx += 1
        while idx < len(self.history_messages) and self.history_messages[idx].get("role") != "user":
            prefix.append(self.history_messages[idx])
            idx += 1
        return prefix, self.history_messages[idx:]

    def _append_trimmed_history(self, message: Dict[str, Any]) -> None:
        self.history_messages.append(message)
        prefix, msgs = self._split_history_prefix()
        limit = len(prefix) + self.max_memory_length * 2
        if len(prefix) + len(msgs) <= limit:
            return
        # Trim in complete step chunks: user -> assistant -> tool (if present)
        while len(prefix) + len(msgs) > limit and msgs:
            # drop earliest user message
            msgs.pop(0)
            # drop corresponding assistant (tool_call) if present
            if msgs and msgs[0].get("role") == "assistant":
                msgs.pop(0)
            # drop corresponding tool result if present
            if msgs and msgs[0].get("role") == "tool":
                msgs.pop(0)
        self.history_messages = prefix + msgs

    def _trim_history_for_long_runs(self) -> None:
        if self._long_run_keep_steps <= 0 or not self.history_messages:
            return
        prefix, msgs = self._split_history_prefix()
        limit = len(prefix) + self._long_run_keep_steps * 2
        while len(prefix) + len(msgs) > limit and msgs:
            msgs.pop(0)
            if msgs and msgs[0].get("role") == "assistant":
                msgs.pop(0)
            if msgs and msgs[0].get("role") == "tool":
                msgs.pop(0)
        self.history_messages = prefix + msgs

    def _record_step(self, thought: str, action: Action, observation: str) -> None:
        self.thoughts.append(thought)
        self.actions.append(action)
        self.observations.append(observation)
        self.responses.append({"thought": thought, "tool": action.__class__.__name__})

    def _call_model(self) -> Tuple[bool, Dict[str, Any]]:
        def _image_msgs():
            imgs = []
            if not self._image_cache:
                return imgs
            qwen_vl_models = {
                "openai_qwen3-vl-235b-a22b-instruct",
                "openai_qwen3-vl-32b-instruct",
                "openai_qwen3-vl-plus",
            }
            is_qwen_vl = self.model in qwen_vl_models

            def _as_data_url(raw: str) -> str:
                raw = (raw or "").strip().strip('"').strip("'")
                if raw.startswith("b'") and raw.endswith("'") and len(raw) > 3:
                    raw = raw[2:-1]

                def _clean_b64(body: str) -> str:
                    import base64

                    body = "".join((body or "").split())
                    missing = len(body) % 4
                    if missing:
                        body = body + ("=" * (4 - missing))
                    try:
                        decoded = base64.b64decode(body, validate=False)
                        return base64.b64encode(decoded).decode("ascii")
                    except Exception:
                        return body

                if raw.startswith("data:"):
                    try:
                        prefix, body = raw.split(",", 1)
                    except Exception:
                        prefix, body = "data:image/png;base64", raw
                    mime = "image/png"
                    try:
                        mime_part = prefix.split("data:", 1)[1]
                        mime = mime_part.split(";")[0] or mime
                    except Exception:
                        pass
                    body = _clean_b64(body)
                    return f"data:{mime};base64,{body}"

                try:
                    p = Path(raw)
                    if p.exists() and p.is_file():
                        import base64
                        import mimetypes

                        mime, _ = mimetypes.guess_type(p.name)
                        mime = mime or "image/png"
                        encoded = base64.b64encode(p.read_bytes()).decode("ascii") #utf-8
                        return f"data:{mime};base64,{encoded}"
                except Exception:
                    pass

                body = _clean_b64(raw)
                return f"data:image/png;base64,{body}"

            for uri in self._image_cache:
                if uri.startswith("http"):
                    url = uri
                elif is_qwen_vl and uri.startswith("data:"):
                    url = uri.strip()
                else:
                    url = _as_data_url(uri)
                if is_qwen_vl and not url.startswith(("http://", "https://", "data:")):
                    url = f"data:image/png;base64,{url}"
                imgs.append({"role": "user", "content": [{"type": "image_url", "image_url": {"url": url}}]})
            return imgs

        payload = {
            "model": self.model,
            "messages": list(self.history_messages) + _image_msgs(),
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "temperature": self.temperature,
            "tools": self.toolset.build_tools_param(),
            "tool_choice": "auto",
            "enable_thinking": True,
        }
        if self.model in {
            "openai_qwen3-235b-a22b",
            "openai_qwen3-30b-a3b",
            "openai_qwen3-8b",
            "openai_qwen3-4b",
            "openai_qwen3-vl-235b-a22b-instruct",
            "openai_qwen3-vl-32b-instruct",
            "openai_qwen3-vl-plus",
        }:
            payload["enable_thinking"] = False
        return call_llm(payload)

    def _prune_unpaired_tool_calls(self) -> None:
        """Best-effort cleanup: ensure assistant tool_calls are paired with tool results."""
        cleaned: List[Dict[str, Any]] = []
        expected = 0
        for msg in self.history_messages:
            role = msg.get("role")
            if role == "assistant" and not msg.get("tool_calls"):
                content = self._normalize_content(msg.get("content"))
                if not content.strip():
                    logger.warning("Dropping empty assistant message without tool_calls.")
                    continue
            if role == "assistant" and msg.get("tool_calls"):
                tool_calls = msg.get("tool_calls") or []
                expected += len(tool_calls)
                cleaned.append(msg)
            elif role == "tool":
                if expected > 0:
                    expected -= 1
                    cleaned.append(msg)
                else:
                    logger.warning("Dropping stray tool message without pending tool_call: %s", msg.get("name"))
            else:
                cleaned.append(msg)
        if expected > 0:
            # Drop trailing assistant tool_calls (and their tool messages) until counts align.
            pruned: List[Dict[str, Any]] = []
            remaining = expected
            for msg in reversed(cleaned):
                role = msg.get("role")
                if remaining > 0 and role == "assistant" and msg.get("tool_calls"):
                    remaining -= len(msg.get("tool_calls") or [])
                    continue
                if remaining > 0 and role == "tool":
                    continue
                pruned.append(msg)
            pruned.reverse()
            cleaned = pruned
            logger.warning("Pruned trailing unmatched tool_calls to recover alignment.")
        self.history_messages = cleaned

    def run(self) -> Tuple[bool, str]:
        assert self.env is not None, "Environment is not set."
        done = False
        result = ""
        step_idx = 0
        observation = self._last_observation

        while not done and step_idx < self.max_steps:
            if self.env is not None:
                logger.info("Step %d/%d for %s", step_idx + 1, self.max_steps, self.env.task_id)
            else:
                logger.info("Step %d/%d", step_idx + 1, self.max_steps)
            self._prune_unpaired_tool_calls()
            if step_idx + 1 > self._long_run_trim_after:
                self._trim_history_for_long_runs()
            reminder_threshold = max(self.max_steps - 10, 1)
            observation_text = observation
            if step_idx + 1 >= reminder_threshold:
                observation_text = (
                    f"{observation}\n\n[Reminder] Final 10 steps. Stop new SQL/Python and call `finish` with the report content."
                )
            self._append_trimmed_history(
                {"role": "user", "content": f"Observation (step {step_idx + 1}/{self.max_steps}): {observation_text}"}
            )
            status, message = self._call_model()

            if not status:
                error_msg = self._normalize_content(message.get("error") if isinstance(message, dict) else message)
                logger.warning("LLM call failed: %s", error_msg)
                self._llm_failure_streak += 1
                if self._llm_failure_streak >= self._max_llm_failure_retries:
                    logger.warning(
                        "Exceeded LLM failure retries (%d); terminating task.",
                        self._max_llm_failure_retries,
                    )
                    return False, (
                        "Auto-stop: LLM call failed repeatedly "
                        f"({self._llm_failure_streak}x). Last error: {error_msg}"
                    )
                if error_msg in {"psm_empty_choices", "psm_call_failed"}:
                    return False, f"LLM call failed: {error_msg}"
                # Some providers (e.g., Gemini) require each tool call to be immediately followed by a tool result.
                # If they complain about mismatched tool counts, drop the latest tool-call turn to re-sync.
                if isinstance(error_msg, str) and (
                    "tool result must follow tool call" in error_msg.lower()
                    or "tool counts must be equal" in error_msg.lower()
                    or "-1013" in error_msg
                ):
                    # Best effort recovery: drop any trailing tool/assistant tool_calls, then hard-reset to system message.
                    while self.history_messages and self.history_messages[-1].get("role") == "tool":
                        self.history_messages.pop()
                    if (
                        self.history_messages
                        and self.history_messages[-1].get("role") == "assistant"
                        and self.history_messages[-1].get("tool_calls")
                    ):
                        dropped = self.history_messages.pop()
                        logger.warning(
                            "Dropped last assistant tool_calls to recover from tool mismatch: %s",
                            dropped.get("tool_calls"),
                        )
                    self._prune_unpaired_tool_calls()
                    if self.history_messages:
                        logger.warning("Resetting history to system message to clear tool mismatch state.")
                        self.history_messages = [self.history_messages[0]]
                    else:
                        self.history_messages = [{"role": "system", "content": self.system_message}]
                    observation = (
                        "Recovered from a tool-call mismatch; context was reset. "
                        "Please continue with the required tool calls (bash/local_db_sql/etc.)."
                    )
                    continue
                observation = f"LLM call failed: {error_msg}"
                continue
            else:
                self._llm_failure_streak = 0

            if not isinstance(message, dict):
                message = {"content": message}
            content = self._normalize_content(message.get("content"))
            tool_calls = self._normalize_tool_calls(message.get("tool_calls") or [])
            if not content.strip():
                content = ""
            else:
                # Enforce balanced <think> tags to keep replies well-formed.
                stripped = content.strip()
                if "<think>" not in stripped:
                    content = f"<think>{content}</think>"
                elif "</think>" not in stripped:
                    content = f"{content}</think>"
            if not tool_calls:
                tool_calls = self._fallback_tool_calls(content)
                if tool_calls:
                    message["tool_calls"] = tool_calls
            for idx, tool_call in enumerate(tool_calls, start=1):
                if not tool_call.get("id"):
                    tool_call["id"] = f"call_{step_idx + 1}_{idx}"
            logger.info("LLM reply: content=%s tool_calls=%s", content, bool(tool_calls))
            assistant_msg: Dict[str, Any] = {"role": "assistant", "content": content}
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
                self._append_trimmed_history(assistant_msg)
            thought = content

            if not tool_calls:
                observation = (
                    "Invalid response: you must return a tool call (bash, local_db_sql, finish). "
                    "Do not answer in plain text."
                )
                logger.info("No tool calls returned; requesting a tool call instead of finishing.")
                self._invalid_tool_call_streak += 1
                if self._invalid_tool_call_streak >= self._max_invalid_tool_call_retries:
                    logger.warning(
                        "Exceeded invalid tool-call retries (%d); terminating task.",
                        self._max_invalid_tool_call_retries,
                    )
                    return True, (
                        "Auto-finish: exceeded consecutive empty tool-call retries "
                        f"({self._max_invalid_tool_call_retries})."
                    )
                continue

            invalid_observation = None
            valid_actions = 0
            for tool_call in tool_calls:
                action = self.toolset.to_action(tool_call)
                logger.info(
                    "Step %d tool_call=%s args=%s parsed_action=%s",
                    step_idx + 1,
                    (tool_call.get("function") or {}).get("name"),
                    (tool_call.get("function") or {}).get("arguments"),
                    action,
                )
                if action is None:
                    raw_args = (tool_call.get("function") or {}).get("arguments")
                    if os.getenv("LLM_DEBUG"):
                        logger.warning(
                            "Invalid tool call raw arguments (len=%s): %s",
                            len(raw_args) if isinstance(raw_args, str) else "n/a",
                            raw_args,
                        )
                    invalid_observation = (
                        "Invalid tool call or missing arguments. "
                        "Please resend a valid tool call with complete JSON arguments and no truncation."
                    )
                    done = False
                    tool_call_id = tool_call.get("id") or f"call_{step_idx + 1}_invalid"
                    self._append_trimmed_history(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "name": (tool_call.get("function") or {}).get("name"),
                            "content": invalid_observation,
                        }
                    )
                    continue
                else:
                    if isinstance(action, Terminate):
                        if not (self._sql_calls > 0 or self._saw_data_probe):
                            observation = (
                                "Blocked Terminate because no database analysis has been performed yet. "
                                "Run local_db_sql or a bash step that queries the database before finish."
                            )
                            done = False
                            logger.info("Blocked premature Terminate; requesting data exploration first.")
                        else:
                            observation, done = self.env.step(action)
                        logger.info("Observation after %s: %s", action.__class__.__name__, observation[:60000])
                        self._record_step(thought, action, observation)
                    else:
                        observation, done = self.env.step(action)
                        if isinstance(action, LoadImage) and observation.startswith("IMAGE_DATA_URI:"):
                            uri = observation.split("IMAGE_DATA_URI:", 1)[1].strip()
                            if uri and uri not in self._image_cache:
                                self._image_cache.append(uri)
                            observation = f"[image_loaded:{os.path.basename(action.file_path)}]"
                        logger.info("Observation after %s: %s", action.__class__.__name__, observation[:60000])
                        if isinstance(action, LOCAL_DB_SQL):
                            self._saw_data_probe = True
                            self._sql_calls += 1
                            self._update_last_db_path(action.file_path or "")
                            if "database file not found" in observation.lower():
                                self._db_missing_streak += 1
                            else:
                                self._db_missing_streak = 0
                        if isinstance(action, Python):
                            self._saw_data_probe = True
                            self._update_last_db_path(observation)
                        if isinstance(action, Bash):
                            self._bash_calls += 1
                            if "sqlite" in str(action.code).lower():
                                self._saw_data_probe = True
                            self._update_last_db_path(observation)
                            if "sqlite" in observation.lower() or "database file" in observation.lower():
                                self._db_missing_streak = 0
                        self._record_step(thought, action, observation)
                    repeat_limit_reached = False
                    action_repr = str(action)
                    if self._last_action_repr == action_repr:
                        self._repeat_action_streak += 1
                    else:
                        self._repeat_action_streak = 1
                        self._last_action_repr = action_repr
                    if self._repeat_action_streak >= self._repeat_action_limit:
                        logger.warning(
                            "Repeated action limit reached (%d): %s",
                            self._repeat_action_limit,
                            action_repr,
                        )
                        observation = (
                            f"{observation}\n\n[Error] Repeated the same action "
                            f"{self._repeat_action_streak} times. Auto-stopping."
                        )
                        repeat_limit_reached = True
                        done = False
                    elif self._repeat_action_streak >= 2:
                        logger.warning("Detected repeated action: %s", action_repr)
                        observation = (
                            f"{observation}\n\n[Warning] You already ran {action_repr} "
                            "multiple times in a row. Switch to a different query or call finish."
                        )
                        done = False
                    if isinstance(action, Terminate):
                        result = action.content or "done"
                tool_call_id = tool_call.get("id") or f"call_{step_idx + 1}_{valid_actions + 1}"
                self._append_trimmed_history(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "name": (tool_call.get("function") or {}).get("name"),
                        "content": observation,
                    }
                )
                valid_actions += 1
                step_idx += 1
                if self._db_missing_streak >= 2:
                    observation = (
                        f"{observation}\n\n[Error] Database file not found twice. "
                        "Use bash to list the actual .sqlite/.db files and retry with the correct filename."
                    )
                    self._append_trimmed_history(
                        {
                            "role": "tool",
                            "tool_call_id": f"{tool_call_id}_db_missing",
                            "name": "system",
                            "content": observation,
                        }
                    )
                    return False, "Auto-stop: database file not found twice; require bash to locate filename."
                if repeat_limit_reached:
                    return False, (
                        "Auto-stop: repeated the same action "
                        f"{self._repeat_action_streak} times: {self._last_action_repr}"
                    )
                if done:
                    break

            if valid_actions == 0:
                observation = invalid_observation or (
                    "Invalid tool call: missing tool name or arguments. Please retry with a valid tool call."
                )
                self._invalid_tool_call_streak += 1
                if self._invalid_tool_call_streak >= self._max_invalid_tool_call_retries:
                    logger.warning(
                        "Exceeded invalid tool-call retries (%d); advancing step.",
                        self._max_invalid_tool_call_retries,
                    )
                    step_idx += 1
                    self._invalid_tool_call_streak = 0
            else:
                self._invalid_tool_call_streak = 0

            self._last_observation = observation

        return done, result

    def get_trajectory(self) -> Dict[str, Any]:
        trajectory = []
        for i in range(len(self.observations)):
            trajectory.append(
                {
                    "observation": self.observations[i],
                    "thought": self.thoughts[i],
                    "action": str(self.actions[i]),
                    "response": self.responses[i],
                }
            )
        return {"Task": self.instruction, "system_message": self.system_message, "trajectory": trajectory}
