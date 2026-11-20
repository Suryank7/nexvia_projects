"""Loop detection and cost/token budget guardrails for the multi-agent workflow.

Extends existing per-run/per-thread tool-call limits with workflow-level
protection: repeated action detection, state-progress tracking, budget
exhaustion, and safe termination.
"""

from __future__ import annotations

from typing import List, Optional, Tuple


from cuga.backend.cuga_graph.nodes.multi_agent.schemas import GuardrailResult
from cuga.config import settings


class LoopDetector:
    """Detects repeated identical agent actions, tool calls, and states."""

    def __init__(self, max_repeats: int = 3):
        self.max_repeats = max_repeats
        self._action_history: List[str] = []
        self._tool_call_history: List[str] = []
        self._state_history: List[str] = []

    def record_action(self, agent: str, action: str, payload_hash: str) -> None:
        entry = f"{agent}:{action}:{payload_hash}"
        self._action_history.append(entry)

    def record_tool_call(self, tool_name: str, args_hash: str) -> None:
        entry = f"{tool_name}:{args_hash}"
        self._tool_call_history.append(entry)

    def record_state(self, state_hash: str) -> None:
        self._state_history.append(state_hash)

    def _count_repeats(self, history: List[str], window: Optional[int] = None) -> int:
        if not history:
            return 0
        recent = history[-window:] if window else history
        last = recent[-1]
        return sum(1 for h in recent if h == last)

    def detect_loop(self) -> Tuple[bool, Optional[str]]:
        """Return (loop_detected, reason)."""

        # Repeated identical agent action
        if self._count_repeats(self._action_history) >= self.max_repeats:
            return True, f"Repeated identical agent action {self.max_repeats} times"

        # Repeated identical tool call
        if self._count_repeats(self._tool_call_history) >= self.max_repeats:
            return True, f"Repeated identical tool call {self.max_repeats} times"

        # Repeated workflow state without progress
        if self._count_repeats(self._state_history) >= self.max_repeats:
            return True, f"Workflow state repeated {self.max_repeats} times without progress"

        return False, None


class BudgetTracker:
    """Tracks token usage, estimated cost, tool calls, and execution time."""

    def __init__(
        self,
        max_iterations: int = 10,
        max_agent_retries: int = 3,
        max_tool_calls: int = 100,
        max_execution_time_seconds: float = 600.0,
        max_tokens: int = 50000,
        max_cost_usd: float = 10.0,
        max_consecutive_rejections: int = 3,
    ):
        self.max_iterations = max_iterations
        self.max_agent_retries = max_agent_retries
        self.max_tool_calls = max_tool_calls
        self.max_execution_time_seconds = max_execution_time_seconds
        self.max_tokens = max_tokens
        self.max_cost_usd = max_cost_usd
        self.max_consecutive_rejections = max_consecutive_rejections

        self.iteration_count = 0
        self.tool_call_count = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost_usd = 0.0
        self.start_time: Optional[float] = None
        self.consecutive_rejections = 0

    def start(self) -> None:
        import time

        self.start_time = time.time()

    def record_iteration(self) -> None:
        self.iteration_count += 1

    def record_tool_call(self) -> None:
        self.tool_call_count += 1

    def record_tokens(self, input_tokens: int, output_tokens: int, cost_usd: float) -> None:
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_cost_usd += cost_usd

    def record_rejection(self) -> None:
        self.consecutive_rejections += 1

    def reset_rejections(self) -> None:
        self.consecutive_rejections = 0

    def elapsed_seconds(self) -> Optional[float]:
        if self.start_time is None:
            return None
        import time

        return time.time() - self.start_time

    def check_budget(self) -> GuardrailResult:
        """Return GuardrailResult indicating whether execution may continue."""

        if self.iteration_count >= self.max_iterations:
            return GuardrailResult(
                allowed=False,
                reason=f"Maximum iterations ({self.max_iterations}) reached",
                termination_reason="max_iterations",
                budget_exhausted=True,
            )

        if self.tool_call_count >= self.max_tool_calls:
            return GuardrailResult(
                allowed=False,
                reason=f"Maximum tool calls ({self.max_tool_calls}) reached",
                termination_reason="max_tool_calls",
                budget_exhausted=True,
            )

        total_tokens = self.total_input_tokens + self.total_output_tokens
        if total_tokens >= self.max_tokens:
            return GuardrailResult(
                allowed=False,
                reason=f"Maximum token usage ({self.max_tokens}) reached",
                termination_reason="max_tokens",
                budget_exhausted=True,
            )

        if self.total_cost_usd >= self.max_cost_usd:
            return GuardrailResult(
                allowed=False,
                reason=f"Maximum estimated cost (${self.max_cost_usd}) reached",
                termination_reason="max_cost",
                budget_exhausted=True,
            )

        if self.elapsed_seconds() is not None and self.elapsed_seconds() >= self.max_execution_time_seconds:
            return GuardrailResult(
                allowed=False,
                reason=f"Maximum execution time ({self.max_execution_time_seconds}s) reached",
                termination_reason="max_execution_time",
                budget_exhausted=True,
            )

        if self.consecutive_rejections >= self.max_consecutive_rejections:
            return GuardrailResult(
                allowed=False,
                reason=f"Maximum consecutive reviewer rejections ({self.max_consecutive_rejections}) reached",
                termination_reason="max_consecutive_rejections",
            )

        return GuardrailResult(allowed=True)


def load_guardrails_from_settings() -> BudgetTracker:
    """Build a BudgetTracker from existing CUGA settings, with conservative defaults."""

    maw = getattr(settings, "multi_agent_workflow", None)
    max_tool_calls = int(getattr(maw, "max_tool_calls", 100) or 100)
    max_tokens = int(getattr(maw, "max_tokens", 50000) or 50000)
    max_cost = float(getattr(maw, "max_cost_usd", 10.0) or 10.0)
    max_time = float(getattr(maw, "max_execution_time_seconds", 600.0) or 600.0)
    max_iterations = int(getattr(maw, "max_iterations", 10) or 10)
    max_retries = int(getattr(maw, "max_agent_retries", 3) or 3)
    max_rejections = int(getattr(maw, "max_consecutive_rejections", 3) or 3)

    return BudgetTracker(
        max_iterations=max_iterations,
        max_agent_retries=max_retries,
        max_tool_calls=max_tool_calls,
        max_execution_time_seconds=max_time,
        max_tokens=max_tokens,
        max_cost_usd=max_cost,
        max_consecutive_rejections=max_rejections,
    )
