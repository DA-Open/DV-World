import json
import logging
import re
from typing import Any, Dict, List, Optional

try:
    from dvworld_agent_fcmode.agent.models import call_llm as _real_call_llm
except Exception:  # pragma: no cover - best effort import
    _real_call_llm = None
from dvworld_agent_fcmode.user_simulator.prompt import (
    ROUTER_TEMPLATE,
    GENERATOR_TEMPLATE,
)
from dvworld_agent_fcmode.user_simulator.trajectory import summarize_trajectory

logger = logging.getLogger("dvworld_agent_fcmode.user_simulator")


def _mask_numbers(text: str) -> str:
    """Lightly obfuscate numbers for hint mode to avoid over-specific answers."""
    return re.sub(r"\d+(?:\.\d+)?", "around that value", text or "")


class UserSimulator:
    """A minimalist 2-stage user simulator for DV-Interact."""

    def __init__(self, fact_sheet: Dict[str, Any], model: str = "gpt-4o-mini", patience: int = 3):
        self.fact_sheet = fact_sheet or {}
        self.model = model
        self.patience = patience
        self.history: List[Dict[str, Any]] = []
        self._consecutive_refusals = 0
        self.router_prompt_rendered = ""
        self.generator_prompt_last = ""

    def step(self, agent_message: str, agent_trajectory: Optional[str] = None) -> str:
        """Handle a single agent message and return the simulated user reply."""
        if not isinstance(agent_message, str):
            agent_message = str(agent_message)
        context_summary = self._summarize_context()
        trajectory_summary = agent_trajectory or self._render_trajectory()
        fact_source_text = self._default_fact_source()
        instruction_text = self._instruction_text()
        router_output = self._run_router(agent_message, context_summary, trajectory_summary, fact_source_text, instruction_text)
        decision = self._parse_router(router_output)

        hint_mode = False
        if decision == "REFUSE":
            self._consecutive_refusals += 1
            if self._consecutive_refusals >= 2:
                hint_mode = True
                decision = "ANSWER"
                fact_source_text = _mask_numbers(fact_source_text or context_summary)
                self._consecutive_refusals = 0
        else:
            self._consecutive_refusals = 0

        if decision in {"REFUSE", "IRRELEVANT"}:
            self.patience = max(self.patience - 1, 0)

        mood = self._mood_description()
        response = self._generate_response(
            agent_message=agent_message,
            fact_source=fact_source_text or context_summary,
            decision=decision,
            hint_mode=hint_mode,
            mood=mood,
            instruction=instruction_text,
            trajectory=trajectory_summary,
        )

        self.history.append(
            {
                "agent": agent_message,
                "decision": decision,
                "hint_mode": hint_mode,
                "response": response,
                "patience": self.patience,
            }
        )
        return response

    def _run_router(self, agent_message: str, context_summary: str, trajectory_summary: str, fact_source: str, instruction: str) -> str:
        prompt = ROUTER_TEMPLATE.format(
            instruction=instruction,
            context_summary=context_summary,
            trajectory_summary=trajectory_summary,
            fact_source=fact_source,
            agent_message=agent_message,
            trajectory=trajectory_summary,
        )
        self.router_prompt_rendered = prompt
        return self._call_llm(prompt)

    def _generate_response(
        self,
        agent_message: str,
        fact_source: str,
        decision: str,
        hint_mode: bool,
        mood: str,
        instruction: str,
        trajectory: str,
    ) -> str:
        if decision == "IRRELEVANT":
            return "That doesn't seem related to what I'm asking for."
        if decision == "REFUSE":
            return "I just need the insights, not code or column names."

        # ANSWER (includes hint_mode path)
        info = _mask_numbers(fact_source) if hint_mode else fact_source
        prompt = GENERATOR_TEMPLATE.format(
            mood_description=mood,
            fact_source=info,
            agent_message=agent_message,
            table_schema=self._table_schema(),
            instruction=instruction,
            trajectory=trajectory,
        )
        self.generator_prompt_last = prompt

        completion = self._call_llm(prompt)
        return completion.strip()

    def _call_llm(self, prompt: str) -> str:
        """Best-effort wrapper around the shared call_llm; falls back to echo."""
        if _real_call_llm:
            try:
                status, resp = _real_call_llm({"model": self.model, "messages": [{"role": "user", "content": prompt}]})
                if status and isinstance(resp, dict):
                    content = resp.get("content") or resp.get("message", {}).get("content")
                    if isinstance(content, list):
                        content = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
                    if content:
                        return str(content)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("LLM call failed, falling back to stub: %s", exc)
        # Stub fallback
        return "ANSWER"

    def _parse_router(self, raw: str) -> str:
        decision = "ANSWER"
        if isinstance(raw, str):
            upper = raw.upper()
            if "REFUSE" in upper:
                decision = "REFUSE"
            elif "ANSWER" in upper:
                decision = "ANSWER"
        return decision

    def _default_fact_source(self) -> str:
        if not isinstance(self.fact_sheet, dict):
            return ""
        if "fact_source" in self.fact_sheet:
            return str(self.fact_sheet.get("fact_source") or "")
        ctx = self.fact_sheet.get("context", {}) or {}
        pieces = []
        for key in ("data_logic", "visual_logic"):
            val = ctx.get(key)
            if val:
                pieces.append(str(val))
        return " | ".join(pieces) if pieces else ""

    def _summarize_context(self) -> str:
        ctx = self.fact_sheet.get("context", {}) if isinstance(self.fact_sheet, dict) else {}
        parts = []
        for key, val in ctx.items():
            if key == "forbidden_terms":
                continue
            if val:
                parts.append(f"{key}: {val}")
        return "; ".join(parts) if parts else "No context provided."

    def _table_schema(self) -> str:
        if not isinstance(self.fact_sheet, dict):
            return ""
        schema = self.fact_sheet.get("table_schema") or ""
        return str(schema)

    def _render_trajectory(self) -> str:
        return summarize_trajectory(self.history, max_turns=5)

    def _instruction_text(self) -> str:
        if isinstance(self.fact_sheet, dict) and "instruction" in self.fact_sheet:
            return str(self.fact_sheet.get("instruction") or "")
        return ""

    def _mood_description(self) -> str:
        if self.patience >= 2:
            return "Helpful, patient, and concise."
        return "Annoyed; keep it brief and a bit curt."
