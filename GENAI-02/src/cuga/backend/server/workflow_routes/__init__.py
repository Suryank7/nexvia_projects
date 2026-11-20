"""FastAPI routes for the multi-agent autonomous workflow.

Endpoints:
  POST   /api/workflow/run              — submit a task
  GET    /api/workflow/state/{task_id}  — view current state / progress
  POST   /api/workflow/approve          — approve/reject/modify an action
  GET    /api/workflow/history          — list workflow runs
  GET    /api/workflow/history/{task_id} — get a single workflow run
  GET    /api/workflow/approvals/{run_id} — get approval history for a run
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel

from cuga.backend.cuga_graph.nodes.multi_agent.schemas import ApprovalDecision
from cuga.backend.cuga_graph.nodes.multi_agent.workflow_persistence import (
    get_workflow_persistence,
)
from cuga.backend.cuga_graph.nodes.multi_agent.workflow import (
    CugaMultiAgentWorkflow,
)

router = APIRouter(prefix="/api/workflow", tags=["multi-agent-workflow"])

_workflow: Optional[CugaMultiAgentWorkflow] = None


def _get_workflow() -> CugaMultiAgentWorkflow:
    global _workflow
    if _workflow is None:
        _workflow = CugaMultiAgentWorkflow()
    return _workflow


class TaskSubmitRequest(BaseModel):
    query: str
    thread_id: Optional[str] = None


class TaskSubmitResponse(BaseModel):
    task_id: str
    run_id: str
    status: str
    message: str


class ApprovalRequest(BaseModel):
    request_id: str
    decision: str  # approve | reject | request_modification
    decided_by: Optional[str] = "human"
    reason: Optional[str] = None


@router.post("/run", response_model=TaskSubmitResponse)
async def submit_task(request: TaskSubmitRequest):
    """Submit a task to the multi-agent autonomous workflow.

    The Planner creates a plan, Researcher gathers information, Coder
    generates and executes code in the sandbox, Reviewer validates, and
    the workflow produces a final result. Risky actions pause for approval.
    """
    if not request.query or not request.query.strip():
        raise HTTPException(status_code=400, detail="query is required")

    workflow = _get_workflow()
    import uuid

    task_id = str(uuid.uuid4())
    thread_id = request.thread_id or str(uuid.uuid4())

    try:
        final_state = await workflow.run(request.query.strip(), thread_id=thread_id)
        return TaskSubmitResponse(
            task_id=task_id,
            run_id=final_state.run_id or "",
            status=final_state.execution_status or "unknown",
            message="Workflow completed"
            if final_state.execution_status == "completed"
            else f"Workflow {final_state.execution_status}",
        )
    except Exception as e:
        logger.exception("Workflow submission failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/state/{task_id}")
async def get_state(task_id: str):
    """View the current execution state and progress for a task."""
    persistence = get_workflow_persistence()
    run = await persistence.get_workflow_run(task_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return JSONResponse(run)


@router.post("/approve")
async def approve_action(request: ApprovalRequest):
    """Approve, reject, or request modification of a pending approval request."""
    persistence = get_workflow_persistence()

    # Find the pending approval request by scanning runs
    runs = await persistence.list_workflow_runs(limit=1000)
    found = None
    for run in runs:
        approvals = await persistence.get_approval_history(run.get("id", ""))
        for ap in approvals:
            if ap.get("id") == request.request_id and ap.get("approval_status") == "pending":
                found = (run, ap)
                break
        if found:
            break

    if not found:
        raise HTTPException(status_code=404, detail=f"Pending approval {request.request_id} not found")

    run, ap = found
    decision = request.decision.lower()
    if decision not in ("approve", "reject", "request_modification"):
        raise HTTPException(
            status_code=400, detail="decision must be approve, reject, or request_modification"
        )

    # Update the approval record
    from cuga.backend.cuga_graph.nodes.multi_agent.schemas import ApprovalRequest as AR

    ar = AR(
        id=ap.get("id"),
        run_id=ap.get("run_id"),
        agent_name=ap.get("agent_name", ""),
        action_type=ap.get("action_type", ""),
        action_payload=ap.get("action_payload", {}),
        risk_level=ap.get("risk_level", "medium"),
        reason=ap.get("approval_reason", ""),
    )
    ar.decision = ApprovalDecision(decision)
    ar.decided_by = request.decided_by or "human"
    ar.decision_reason = request.reason or ""
    ar.status = "approved" if decision == "approve" else "rejected"

    await persistence.update_approval_request(ar)

    return {
        "ok": True,
        "request_id": request.request_id,
        "decision": decision,
        "message": f"Action {decision}d",
    }


@router.get("/history")
async def list_history(limit: int = 50):
    """List workflow execution history."""
    persistence = get_workflow_persistence()
    runs = await persistence.list_workflow_runs(limit=limit)
    return {"runs": runs, "count": len(runs)}


@router.get("/history/{task_id}")
async def get_history(task_id: str):
    """Get a single workflow run by task ID."""
    persistence = get_workflow_persistence()
    run = await persistence.get_workflow_run(task_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    approvals = await persistence.get_approval_history(run.get("id", ""))
    return {"run": run, "approvals": approvals}


@router.get("/approvals/{run_id}")
async def get_approvals(run_id: str):
    """Get approval history for a specific run."""
    persistence = get_workflow_persistence()
    approvals = await persistence.get_approval_history(run_id)
    return {"run_id": run_id, "approvals": approvals}


@router.get("/plan/{task_id}")
async def get_plan(task_id: str):
    """Get the execution plan for a task."""
    persistence = get_workflow_persistence()
    run = await persistence.get_workflow_run(task_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return {
        "task_id": run.get("task_id"),
        "execution_plan": run.get("execution_plan"),
        "status": run.get("status"),
    }
