"""PostgreSQL persistence layer for multi-agent workflow execution history.

Tables (additive — existing tables are untouched):
  workflow_runs, agent_executions, approval_history, tool_execution_history

Reuses the existing ProdRelationalStore (asyncpg) connection pool via
StorageFacade. Falls back gracefully when storage.mode != prod.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


from cuga.backend.storage.facade import get_storage


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkflowPersistence:
    """CRUD for workflow execution history tables."""

    def __init__(self, store=None, db_name: str = "cuga"):
        self._store = store
        self._db_name = db_name
        self._initialized = False

    async def _store(self):
        if self._store is None:
            facade = get_storage()
            self._store = facade.get_relational_store(self._db_name)
        return self._store

    async def _ensure_tables(self) -> None:
        """Create tables if they don't exist (idempotent)."""
        if self._initialized:
            return
        store = await self._store()
        statements = self._ddl_statements()
        await store.execute_batch(statements)
        self._initialized = True

    @staticmethod
    def _ddl_statements() -> List[tuple]:
        return [
            (
                """
                CREATE TABLE IF NOT EXISTS workflow_runs (
                    id VARCHAR(64) PRIMARY KEY,
                    task_id VARCHAR(64) NOT NULL,
                    user_request TEXT NOT NULL,
                    status VARCHAR(32) NOT NULL DEFAULT 'pending',
                    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    completed_at TIMESTAMPTZ,
                    execution_plan JSONB,
                    final_result TEXT,
                    total_iterations INTEGER DEFAULT 0,
                    total_tool_calls INTEGER DEFAULT 0,
                    total_tokens INTEGER DEFAULT 0,
                    estimated_cost DOUBLE PRECISION DEFAULT 0,
                    error_summary TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_workflow_runs_task_id ON workflow_runs(task_id);
                CREATE INDEX IF NOT EXISTS idx_workflow_runs_status ON workflow_runs(status);
                """,
                (),
            ),
            (
                """
                CREATE TABLE IF NOT EXISTS agent_executions (
                    id VARCHAR(64) PRIMARY KEY,
                    run_id VARCHAR(64) NOT NULL,
                    agent_name VARCHAR(64) NOT NULL,
                    node_name VARCHAR(64) NOT NULL,
                    input_summary TEXT,
                    output_summary TEXT,
                    status VARCHAR(32) NOT NULL DEFAULT 'pending',
                    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    completed_at TIMESTAMPTZ,
                    token_usage JSONB,
                    estimated_cost DOUBLE PRECISION DEFAULT 0,
                    error_details TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_agent_executions_run_id ON agent_executions(run_id);
                CREATE INDEX IF NOT EXISTS idx_agent_executions_agent_name ON agent_executions(agent_name);
                """,
                (),
            ),
            (
                """
                CREATE TABLE IF NOT EXISTS approval_history (
                    id VARCHAR(64) PRIMARY KEY,
                    run_id VARCHAR(64) NOT NULL,
                    agent_name VARCHAR(64) NOT NULL,
                    action_type VARCHAR(64) NOT NULL,
                    action_payload JSONB,
                    risk_level VARCHAR(16) NOT NULL DEFAULT 'medium',
                    approval_status VARCHAR(16) NOT NULL DEFAULT 'pending',
                    approved_by VARCHAR(64),
                    approval_reason TEXT,
                    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    decided_at TIMESTAMPTZ
                );
                CREATE INDEX IF NOT EXISTS idx_approval_history_run_id ON approval_history(run_id);
                CREATE INDEX IF NOT EXISTS idx_approval_history_status ON approval_history(approval_status);
                """,
                (),
            ),
            (
                """
                CREATE TABLE IF NOT EXISTS tool_execution_history (
                    id VARCHAR(64) PRIMARY KEY,
                    run_id VARCHAR(64) NOT NULL,
                    agent_name VARCHAR(64) NOT NULL,
                    tool_name VARCHAR(128) NOT NULL,
                    tool_input_summary TEXT,
                    tool_output_summary TEXT,
                    status VARCHAR(32) NOT NULL DEFAULT 'pending',
                    execution_duration DOUBLE PRECISION DEFAULT 0,
                    error_details TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_tool_exec_history_run_id ON tool_execution_history(run_id);
                CREATE INDEX IF NOT EXISTS idx_tool_exec_history_tool_name ON tool_execution_history(tool_name);
                """,
                (),
            ),
        ]

    # ------------------------------------------------------------------
    # Workflow runs
    # ------------------------------------------------------------------

    async def create_workflow_run(
        self,
        task_id: str,
        run_id: str,
        user_request: str,
        execution_plan: Dict[str, Any],
    ) -> None:
        await self._ensure_tables()
        store = await self._store()
        await store.execute(
            """
            INSERT INTO workflow_runs
                (id, task_id, user_request, status, started_at, execution_plan)
            VALUES ($1, $2, $3, 'in_progress', NOW(), $4)
            ON CONFLICT (id) DO NOTHING
            """,
            (run_id, task_id, user_request, json.dumps(execution_plan)),
        )

    async def update_workflow_run(
        self,
        task_id: str,
        status: Optional[str] = None,
        final_result: Optional[str] = None,
        total_iterations: Optional[int] = None,
        total_tool_calls: Optional[int] = None,
        total_tokens: Optional[int] = None,
        estimated_cost: Optional[float] = None,
        error_summary: Optional[str] = None,
    ) -> None:
        await self._ensure_tables()
        store = await self._store()
        sets = []
        params: List[Any] = []
        idx = 1
        if status is not None:
            sets.append(f"status = ${idx}")
            params.append(status)
            idx += 1
        if final_result is not None:
            sets.append(f"final_result = ${idx}")
            params.append(final_result)
            idx += 1
        if total_iterations is not None:
            sets.append(f"total_iterations = ${idx}")
            params.append(total_iterations)
            idx += 1
        if total_tool_calls is not None:
            sets.append(f"total_tool_calls = ${idx}")
            params.append(total_tool_calls)
            idx += 1
        if total_tokens is not None:
            sets.append(f"total_tokens = ${idx}")
            params.append(total_tokens)
            idx += 1
        if estimated_cost is not None:
            sets.append(f"estimated_cost = ${idx}")
            params.append(estimated_cost)
            idx += 1
        if error_summary is not None:
            sets.append(f"error_summary = ${idx}")
            params.append(error_summary)
            idx += 1
        if status in ("completed", "failed", "terminated", "rejected"):
            sets.append("completed_at = NOW()")
        if not sets:
            return
        params.append(task_id)
        sql = f"UPDATE workflow_runs SET {', '.join(sets)} WHERE task_id = ${idx}"
        await store.execute(sql, tuple(params))

    async def get_workflow_run(self, task_id: str) -> Optional[Dict[str, Any]]:
        await self._ensure_tables()
        store = await self._store()
        return await store.fetchone("SELECT * FROM workflow_runs WHERE task_id = $1", (task_id,))

    async def list_workflow_runs(self, limit: int = 50) -> List[Dict[str, Any]]:
        await self._ensure_tables()
        store = await self._store()
        return await store.fetchall("SELECT * FROM workflow_runs ORDER BY started_at DESC LIMIT $1", (limit,))

    # ------------------------------------------------------------------
    # Agent executions
    # ------------------------------------------------------------------

    async def record_agent_executions(self, run_id: str, state_dict: Dict[str, Any]) -> None:
        await self._ensure_tables()
        store = await self._store()
        agent_roles = ["PlannerAgent", "ResearcherAgent", "CoderAgent", "ReviewerAgent"]
        for role in agent_roles:
            exec_id = f"{run_id}:{role}"
            await store.execute(
                """
                INSERT INTO agent_executions
                    (id, run_id, agent_name, node_name, input_summary, output_summary, status,
                     started_at, completed_at, token_usage, estimated_cost, error_details)
                VALUES ($1, $2, $3, $4, $5, $6, $7, NOW(), NOW(), $8, $9, $10)
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    exec_id,
                    run_id,
                    role,
                    role,
                    state_dict.get("input", ""),
                    state_dict.get("final_output", ""),
                    state_dict.get("execution_status", "pending"),
                    json.dumps(state_dict.get("token_usage", {})),
                    state_dict.get("estimated_cost", 0.0),
                    "; ".join(e.get("message", "") for e in (state_dict.get("errors") or [])) or None,
                ),
            )

    # ------------------------------------------------------------------
    # Approval history
    # ------------------------------------------------------------------

    async def create_approval_request(self, approval) -> None:
        await self._ensure_tables()
        store = await self._store()
        payload = approval.model_dump() if hasattr(approval, "model_dump") else approval
        await store.execute(
            """
            INSERT INTO approval_history
                (id, run_id, agent_name, action_type, action_payload, risk_level,
                 approval_status, requested_at)
            VALUES ($1, $2, $3, $4, $5, $6, 'pending', NOW())
            ON CONFLICT (id) DO NOTHING
            """,
            (
                payload.get("id"),
                payload.get("run_id"),
                payload.get("agent_name"),
                payload.get("action_type"),
                json.dumps(payload.get("action_payload", {})),
                payload.get("risk_level", "medium"),
            ),
        )

    async def update_approval_request(self, approval) -> None:
        await self._ensure_tables()
        store = await self._store()
        payload = approval.model_dump() if hasattr(approval, "model_dump") else approval
        await store.execute(
            """
            UPDATE approval_history
            SET approval_status = $1, decided_at = NOW(), approved_by = $2, approval_reason = $3
            WHERE id = $4
            """,
            (
                "approved" if payload.get("decision") == "approve" else "rejected",
                payload.get("decided_by"),
                payload.get("decision_reason"),
                payload.get("id"),
            ),
        )

    async def get_approval_history(self, run_id: str) -> List[Dict[str, Any]]:
        await self._ensure_tables()
        store = await self._store()
        return await store.fetchall(
            "SELECT * FROM approval_history WHERE run_id = $1 ORDER BY requested_at DESC",
            (run_id,),
        )

    # ------------------------------------------------------------------
    # Tool execution history
    # ------------------------------------------------------------------

    async def record_tool_execution(
        self,
        run_id: str,
        agent_name: str,
        tool_name: str,
        input_summary: str,
        output_summary: str,
        status: str = "completed",
        duration_ms: float = 0.0,
        error_details: Optional[str] = None,
    ) -> None:
        await self._ensure_tables()
        store = await self._store()
        await store.execute(
            """
            INSERT INTO tool_execution_history
                (id, run_id, agent_name, tool_name, tool_input_summary, tool_output_summary,
                 status, execution_duration, error_details, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
            ON CONFLICT (id) DO NOTHING
            """,
            (
                f"{run_id}:{tool_name}:{agent_name}",
                run_id,
                agent_name,
                tool_name,
                input_summary,
                output_summary,
                status,
                duration_ms,
                error_details,
            ),
        )

    async def close(self) -> None:
        pass


_persistence: Optional[WorkflowPersistence] = None


def get_workflow_persistence() -> WorkflowPersistence:
    global _persistence
    if _persistence is None:
        _persistence = WorkflowPersistence()
    return _persistence
