"""Custom OpenTelemetry tracing for the multi-agent workflow.

Adds spans for workflow creation, planner/researcher/coder/reviewer execution,
node transitions, MCP invocations, Playwright sessions, E2B executions,
PostgreSQL operations, human approval requests/decisions, and completion.

Preserves distributed trace context across workflow transitions. Metrics are
captured via span attributes and a lightweight in-memory counter registry.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from loguru import logger

try:
    from opentelemetry import trace as otel_trace
    from opentelemetry.trace import Span
    from opentelemetry.trace.status import Status, StatusCode

    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False

    class Span:  # type: ignore[no-redef]
        def set_attribute(self, key, value):  # noqa: D401
            pass

        def set_status(self, status):  # noqa: D401
            pass

        def end(self):  # noqa: D401
            pass

    class Status:  # type: ignore[no-redef]
        def __init__(self, code, description=""):
            self.code = code
            self.description = description

    class StatusCode:  # type: ignore[no-redef]
        OK = "OK"
        ERROR = "ERROR"


class WorkflowMetrics:
    """In-memory metric counters for workflow execution behavior."""

    def __init__(self):
        self._counters: Dict[str, int] = {}
        self._durations: Dict[str, list[float]] = {}

    def increment(self, name: str, value: int = 1) -> None:
        self._counters[name] = self._counters.get(name, 0) + value

    def record_duration(self, name: str, seconds: float) -> None:
        self._durations.setdefault(name, []).append(seconds)

    def snapshot(self) -> Dict[str, Any]:
        return {
            "counters": dict(self._counters),
            "durations": {
                k: {"count": len(v), "avg_ms": (sum(v) / len(v) * 1000) if v else 0}
                for k, v in self._durations.items()
            },
        }


metrics = WorkflowMetrics()


class WorkflowTracer:
    """Custom tracer emitting workflow-specific OpenTelemetry spans."""

    def __init__(self, service_name: str = "cuga-multi-agent-workflow"):
        self.service_name = service_name
        self._tracer = None
        self._initialized = False

    def _ensure(self):
        if self._initialized:
            return
        self._initialized = True
        if not _OTEL_AVAILABLE:
            logger.debug("OpenTelemetry not available; workflow tracing is a no-op")
            return
        try:
            provider = otel_trace.get_tracer_provider()
            if provider is not None:
                self._tracer = provider.get_tracer(self.service_name)
        except Exception as e:
            logger.debug(f"WorkflowTracer could not acquire OTel tracer: {e}")

    @contextmanager
    def span(
        self,
        name: str,
        *,
        task_id: Optional[str] = None,
        run_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        node_name: Optional[str] = None,
        tool_name: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ):
        """Yield a context manager that opens/closes a workflow span.

        When OpenTelemetry is unavailable this is a no-op context manager.
        """
        self._ensure()
        start = datetime.now(timezone.utc)

        if self._tracer is None:
            yield None
            return

        attrs: Dict[str, Any] = {}
        if task_id:
            attrs["task_id"] = task_id
        if run_id:
            attrs["run_id"] = run_id
        if agent_name:
            attrs["agent_name"] = agent_name
        if node_name:
            attrs["node_name"] = node_name
        if tool_name:
            attrs["tool_name"] = tool_name
        if attributes:
            attrs.update(attributes)

        span = self._tracer.start_span(name, attributes=attrs)
        try:
            with span:
                yield span
        except Exception as exc:
            try:
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                span.set_attribute("error", True)
                span.set_attribute("error.message", str(exc)[:500])
            except Exception:
                pass
            metrics.increment(f"workflow.span.error.{name}")
            raise
        finally:
            try:
                duration = (datetime.now(timezone.utc) - start).total_seconds()
                span.set_attribute("duration_seconds", duration)
                metrics.record_duration(f"workflow.span.{name}", duration)
            except Exception:
                pass

    def start_span(
        self,
        name: str,
        *,
        task_id: Optional[str] = None,
        run_id: Optional[str] = None,
        agent_name: Optional[str] = None,
        node_name: Optional[str] = None,
        tool_name: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ):
        """Return a context-manager span (delegates to ``span``)."""
        return self.span(
            name=name,
            task_id=task_id,
            run_id=run_id,
            agent_name=agent_name,
            node_name=node_name,
            tool_name=tool_name,
            attributes=attributes,
        )

    # Convenience span factories -------------------------------------------------

    def workflow_created(self, task_id: str, run_id: str, user_request: str):
        return self.span(
            "workflow.created",
            task_id=task_id,
            run_id=run_id,
            node_name="Workflow",
            attributes={"user_request": user_request[:500]},
        )

    def planner_execution(self, task_id: str, run_id: str):
        return self.span(
            "agent.planner",
            task_id=task_id,
            run_id=run_id,
            agent_name="PlannerAgent",
            node_name="Planner",
        )

    def researcher_execution(self, task_id: str, run_id: str):
        return self.span(
            "agent.researcher",
            task_id=task_id,
            run_id=run_id,
            agent_name="ResearcherAgent",
            node_name="Researcher",
        )

    def coder_execution(self, task_id: str, run_id: str):
        return self.span(
            "agent.coder",
            task_id=task_id,
            run_id=run_id,
            agent_name="CoderAgent",
            node_name="Coder",
        )

    def reviewer_execution(self, task_id: str, run_id: str):
        return self.span(
            "agent.reviewer",
            task_id=task_id,
            run_id=run_id,
            agent_name="ReviewerAgent",
            node_name="Reviewer",
        )

    def human_approval(self, task_id: str, run_id: str, agent_name: str):
        return self.span(
            "human.approval",
            task_id=task_id,
            run_id=run_id,
            agent_name=agent_name,
            node_name="ApprovalGate",
        )

    def mcp_invoke(self, task_id: str, run_id: str, tool_name: str):
        return self.span(
            "mcp.invoke",
            task_id=task_id,
            run_id=run_id,
            node_name="MCP",
            tool_name=tool_name,
        )

    def playwright_session(self, task_id: str, run_id: str):
        return self.span(
            "playwright.session",
            task_id=task_id,
            run_id=run_id,
            node_name="Playwright",
        )

    def e2b_execution(self, task_id: str, run_id: str):
        return self.span(
            "e2b.execution",
            task_id=task_id,
            run_id=run_id,
            node_name="E2B",
        )

    def postgresql_operation(self, task_id: str, run_id: str, operation: str):
        return self.span(
            "postgresql.operation",
            task_id=task_id,
            run_id=run_id,
            node_name="PostgreSQL",
            attributes={"db_operation": operation},
        )

    def workflow_completed(self, task_id: str, run_id: str, status: str):
        return self.span(
            "workflow.completed",
            task_id=task_id,
            run_id=run_id,
            node_name="Workflow",
            attributes={"final_status": status},
        )


_tracer: Optional[WorkflowTracer] = None


def get_workflow_tracer() -> WorkflowTracer:
    global _tracer
    if _tracer is None:
        _tracer = WorkflowTracer()
    return _tracer
