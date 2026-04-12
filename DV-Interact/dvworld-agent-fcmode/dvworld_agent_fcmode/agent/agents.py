import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dvworld_agent_fcmode.agent.prompts import DVWORLD_SYSTEM_INTERACT
from dvworld_agent_fcmode.agent.action import Action, Terminate, Bash, Python, LOCAL_DB_SQL, AskUser
from dvworld_agent_fcmode.agent.models import call_llm
from dvworld_agent_fcmode.agent.tools import SpiderToolset
from dvworld_agent_fcmode.envs.spider_agent import Spider_Agent_Env
from dvworld_agent_fcmode.envs.utils import calculate_sha256
from dvworld_agent_fcmode.user_simulator import UserSimulator

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
        enable_user_simulator: bool = False,
        user_simulator_model: Optional[str] = None,
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
        self.use_seed_prompt = False
        self.enable_user_simulator = enable_user_simulator
        self.user_simulator_model = user_simulator_model or model

        self.thoughts: List[str] = []
        self.responses: List[Any] = []
        self.actions: List[Action] = []
        self.observations: List[str] = []
        self.system_message = ""
        self.history_messages: List[Dict[str, Any]] = []
        self.env: Optional[Spider_Agent_Env] = None
        self.work_dir = "/workspace"
        self.toolset = SpiderToolset(language=self.language, enable_user_simulator=self.enable_user_simulator)
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
        self.user_simulator: Optional[UserSimulator] = None
        self.ask_user_calls = 0
        self.user_refusals = 0
        self.user_dialogue: List[Dict[str, Any]] = []

    def _render_action_space(self) -> str:
        """Return a concise action space listing for the system prompt."""
        lines = []
        for tool in self.toolset._tools:
            lines.append(f"- {tool.name}: {tool.description}")
        return "\n".join(lines)

        self.user_simulator: Optional[UserSimulator] = None

    def set_env_and_task(self, env: Spider_Agent_Env):
        self.env = env
        self.thoughts.clear()
        self.responses.clear()
        self.actions.clear()
        self.observations.clear()
        self.history_messages.clear()
        self.instruction = self.env.task_config["instruction"]
        self.toolset = SpiderToolset(language=self.language, enable_user_simulator=self.enable_user_simulator)
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
        self._last_observation = "You are in the folder now."
        self.ask_user_calls = 0
        self.user_refusals = 0
        self.user_dialogue = []
        # Instantiate user simulator per task if enabled
        if self.enable_user_simulator:
            fact_sheet = {}
            if isinstance(self.env.task_config, dict):
                fact_sheet = self.env.task_config.get("fact_sheet", {}) or {}
            self.user_simulator = UserSimulator(fact_sheet=fact_sheet, model=self.user_simulator_model)
        else:
            self.user_simulator = None

        self.system_message = DVWORLD_SYSTEM_INTERACT.format(
            work_dir=self.work_dir,
            max_steps=self.max_steps,
            task=self.instruction,
        )

        self.history_messages.append({"role": "system", "content": self.system_message})

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
        payload = {
            "model": self.model,
            "messages": self.history_messages,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "temperature": self.temperature,
            "tools": self.toolset.build_tools_param(),
            "tool_choice": "auto",
            "enable_thinking": True,
        }
        if self.model == "openai_qwen3-coder-plus":
            payload["tools"] = []
            payload["tool_choice"] = "none"
            payload["enable_thinking"] = False
        if self.model in {
            "openai_qwen3-235b-a22b",
            "openai_qwen3-30b-a3b",
            "openai_qwen3-8b",
            "openai_qwen3-4b",
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
                    elif isinstance(action, AskUser):
                        if not self.user_simulator:
                            observation = "User simulator disabled."
                            done = False
                        else:
                            observation = self.user_simulator.step(
                                action.message, agent_trajectory=self._render_agent_trajectory_for_user()
                            )
                            self.ask_user_calls += 1
                            decision = ""
                            if self.user_simulator.history:
                                decision = str(self.user_simulator.history[-1].get("decision", "")).upper()
                                if decision == "REFUSE":
                                    self.user_refusals += 1
                            self.user_dialogue.append(
                                {
                                    "agent": action.message,
                                    "user": observation,
                                    "decision": decision or "ANSWER",
                                }
                            )
                            done = False
                        logger.info("Observation after %s: %s", action.__class__.__name__, observation[:60000])
                        self._record_step(thought, action, observation)
                    else:
                        observation, done = self.env.step(action)
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

        self._write_user_simulation_log()
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

    def _render_agent_trajectory_for_user(self, max_steps: int = 5) -> str:
        """Render recent agent trajectory for user simulator in a REACT-like format."""
        chunks: List[str] = []
        start = max(0, len(self.observations) - max_steps)
        for idx, i in enumerate(range(start, len(self.observations)), start=start + 1):
            thought = self.thoughts[i] if i < len(self.thoughts) else ""
            action = str(self.actions[i]) if i < len(self.actions) else ""
            obs = self.observations[i]
            chunks.append(f"Step {i+1}:\nThought: {thought}\nAction: {action}\nObservation: {obs}")
        return "\n---\n".join(chunks) if chunks else "No prior questions."

    def _write_user_simulation_log(self) -> None:
        if not self.enable_user_simulator or not self.env:
            return
        try:
            root = getattr(self.env, "mnt_dir", None)
            if not root:
                return
            out_dir = Path(root) / "dvworld"
            out_dir.mkdir(parents=True, exist_ok=True)
            payload = {
                "ask_user_calls": self.ask_user_calls,
                "user_refusals": self.user_refusals,
                "dialogue": self.user_dialogue,
                "agent_system_prompt": self.system_message,
                "user_simulator_router_prompt": getattr(self.user_simulator, "router_prompt_rendered", ""),
                "user_simulator_generator_prompt": getattr(self.user_simulator, "generator_prompt_last", ""),
            }
            out_path = out_dir / "user_simulation.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning("Failed to write user simulation log: %s", exc)
