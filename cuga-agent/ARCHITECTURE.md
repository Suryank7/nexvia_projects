# Multi-Agent Autonomous Workflow — Architecture

CUGA's Multi-Agent Autonomous Workflow (MAW) system orchestrates four specialized
agents — Planner, Researcher, Coder, and Reviewer — through a LangGraph state
machine. It runs inside the existing CUGA Agent server and reuses the project's
settings, guardrails, observability, and persistence layers.

## Agents

| Agent | Responsibility |
|---|---|
| Planner | Breaks a user objective into an `ExecutionPlan` with subtasks, dependencies, agent assignments, tool requirements, and risk classification. |
| Researcher | Gathers information from MCP/web/browser sources and returns structured `ResearchResult` objects. |
| Coder | Generates sandboxed Python code and executes it through CUGA's existing sandbox runner. |
| Reviewer | Validates plans, research, and code execution; returns a `ReviewOutput` with approve/revise/reject recommendations. |

Each agent falls back to deterministic behavior when no LLM model is configured, so the workflow is testable without a live provider.

## Workflow graph

The LangGraph (`CugaMultiAgentWorkflow`) is defined in
`src/cuga/backend/cuga_graph/nodes/multi_agent/workflow.py`. Nodes correspond to
the four agents plus planning/review routing. Conditional edges route between
agents based on review outcomes, and interrupt-based approval pauses execution
for risky actions until a human approves, rejects, or requests modification.

State flows through `AgentState` (`src/cuga/backend/cuga_graph/state/agent_state.py`),
extended with additive workflow fields: `execution_plan`, `subtasks`,
`agent_assignments`, `research_results`, `generated_code`,
`sandbox_execution_results`, `review_results`, `tool_calls`,
`approval_requests`, `approval_results`, `execution_status`, `retry_count`,
`iteration_count`, `token_usage`, `estimated_cost`, `errors`, `execution_logs`,
and `final_output`.

## Guardrails

Two guardrail classes live in `guardrails.py`:

- `LoopDetector` — tracks action/tool-call/state history and flags repeated
  identical executions (`max_repeats`, default 3).
- `BudgetTracker` — enforces limits on iterations, tool calls, tokens, cost,
  execution time, and consecutive reviewer rejections. Built from settings via
  `load_guardrails_from_settings()` under the `[multi_agent_workflow]` config
  section.

Both return a `GuardrailResult` (`allowed`, `reason`, `budget_exhausted`,
`loop_detected`) that the workflow consults before proceeding.

## Persistence and tracing

- `WorkflowPersistence` (`workflow_persistence.py`) — CRUD over PostgreSQL
  tables defined in `src/cuga/backend/storage/migrations/001_workflow_history.sql`:
  `workflow_runs`, `agent_executions`, `approval_history`,
  `tool_execution_history`.
- `WorkflowTracer` (`workflow_tracer.py`) — custom OpenTelemetry spans and a
  `WorkflowMetrics` counter for observability.

## API

Endpoints are mounted under `/api/workflow` in
`src/cuga/backend/server/workflow_routes/__init__.py` and registered in
`src/cuga/backend/server/main.py`:

- `POST /api/workflow/run` — submit a task
- `GET /api/workflow/state/{task_id}` — view current state/progress
- `POST /api/workflow/approve` — approve/reject/modify a pending action
- `GET /api/workflow/history` — list workflow runs
- `GET /api/workflow/history/{task_id}` — get a single run
- `GET /api/workflow/approvals/{run_id}` — approval history for a run
- `GET /api/workflow/plan/{task_id}` — execution plan for a task

## Configuration

Added to `src/cuga/settings.toml` under `[multi_agent_workflow]`:

```toml
[multi_agent_workflow]
enabled = true
max_tool_calls = 100
max_tokens = 50000
max_cost_usd = 10.0
max_execution_time_seconds = 600.0
max_iterations = 10
max_agent_retries = 3
max_consecutive_rejections = 3
max_repeats = 3
```

## Testing

Unit tests live in `tests/unit/evaluation/` and are marked `@pytest.mark.unit`.
They cover the 20-task dataset, agent behavior (deterministic fallback), guardrails,
schema validation, and a report generator. Run with:

```bash
uv run pytest tests/unit/evaluation/ -m unit
```
