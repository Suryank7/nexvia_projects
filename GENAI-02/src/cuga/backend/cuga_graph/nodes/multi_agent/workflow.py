"""LangGraph workflow connecting the four specialized agents.

Workflow:
  START -> Planner -> Researcher -> Coder -> Reviewer
    -> Approval Gate (when required) -> Finalization -> END

Conditional edges:
- Research failure -> retry research within limits
- Code validation failure -> feedback to coder
- Reviewer rejection -> return to appropriate agent
- Risky action -> interrupt for human approval
- Human rejection -> safe termination or revision
- Successful review -> finalize
- Budget exhausted / max iterations -> safe termination
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.types import Command, interrupt
from loguru import logger

from cuga.backend.cuga_graph.nodes.multi_agent.agents import (
    CoderAgent,
    PlannerAgent,
    ResearcherAgent,
    ReviewerAgent,
)
from cuga.backend.cuga_graph.nodes.multi_agent.guardrails import (
    LoopDetector,
    load_guardrails_from_settings,
)
from cuga.backend.cuga_graph.nodes.multi_agent.schemas import (
    AgentRole,
    ApprovalDecision,
    ApprovalRequest,
    ExecutionStatus,
    ResearchResult,
    RiskLevel,
)
from cuga.backend.cuga_graph.nodes.multi_agent.workflow_persistence import (
    WorkflowPersistence,
    get_workflow_persistence,
)
from cuga.backend.cuga_graph.nodes.multi_agent.workflow_tracer import WorkflowTracer
from cuga.backend.cuga_graph.state.agent_state import AgentState
from cuga.config import settings


# Node names
PLANNER_NODE = "Planner"
RESEARCHER_NODE = "Researcher"
CODER_NODE = "Coder"
REVIEWER_NODE = "Reviewer"
APPROVAL_NODE = "ApprovalGate"
FINALIZE_NODE = "Finalize"

# Default limits
DEFAULT_MAX_RESEARCH_RETRIES = 2
DEFAULT_MAX_CODE_RETRIES = 2
DEFAULT_MAX_REVIEW_ROUNDS = 3


class CugaMultiAgentWorkflow:
    """LangGraph state machine for the multi-agent autonomous workflow."""

    def __init__(
        self,
        checkpointer=None,
        tracer: Optional[WorkflowTracer] = None,
        persistence: Optional[WorkflowPersistence] = None,
        max_research_retries: Optional[int] = None,
        max_code_retries: Optional[int] = None,
        max_review_rounds: int = DEFAULT_MAX_REVIEW_ROUNDS,
    ):
        self.planner = PlannerAgent()
        self.researcher = ResearcherAgent()
        self.coder = CoderAgent()
        self.reviewer = ReviewerAgent()
        self.tracer = tracer or WorkflowTracer()
        self.persistence = persistence or get_workflow_persistence()
        maw = getattr(settings, "multi_agent_workflow", None)
        self.max_research_retries = (
            max_research_retries
            if max_research_retries is not None
            else int(
                getattr(maw, "max_research_retries", DEFAULT_MAX_RESEARCH_RETRIES)
                or DEFAULT_MAX_RESEARCH_RETRIES
            )
        )
        self.max_code_retries = (
            max_code_retries
            if max_code_retries is not None
            else int(getattr(maw, "max_code_retries", DEFAULT_MAX_CODE_RETRIES) or DEFAULT_MAX_CODE_RETRIES)
        )
        self.max_review_rounds = max_review_rounds
        self.checkpointer = checkpointer
        self.graph = None

    # ------------------------------------------------------------------
    # Node handlers
    # ------------------------------------------------------------------

    async def _planner_node(self, state: AgentState) -> Command:
        task_id = state.task_id or str(uuid.uuid4())
        run_id = state.run_id or str(uuid.uuid4())
        state.task_id = task_id
        state.run_id = run_id
        state.execution_status = ExecutionStatus.IN_PROGRESS.value
        state.iteration_count = (state.iteration_count or 0) + 1

        with self.tracer.span("planner_execution", task_id=task_id, run_id=run_id, agent_name="PlannerAgent"):
            plan = await self.planner.plan(state.input or "", task_id, run_id)

        # Persist plan
        state.execution_plan = plan.model_dump()
        state.subtasks = [st.model_dump() for st in plan.subtasks]
        state.agent_assignments = {st.id: st.assigned_agent.value for st in plan.subtasks}
        state.token_usage = {
            "planner_input_tokens": 0,
            "planner_output_tokens": 0,
        }

        # Persist to DB
        await self.persistence.create_workflow_run(task_id, run_id, state.input or "", plan.model_dump())

        # Review the plan first
        review = await self.reviewer.review_plan(plan, task_id)
        state.review_results = [review.model_dump()]

        if review.final_recommendation == "revise" and review.failed_checks:
            # Send back to planner with feedback
            state.errors = state.errors or []
            state.errors.append(
                {
                    "node": "Planner",
                    "type": "plan_revision",
                    "message": "; ".join(review.identified_issues),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            return Command(
                update=state.model_dump(),
                goto=PLANNER_NODE,
            )

        return Command(
            update=state.model_dump(),
            goto=RESEARCHER_NODE,
        )

    async def _researcher_node(self, state: AgentState) -> Command:
        task_id = state.task_id
        run_id = state.run_id

        with self.tracer.span(
            "researcher_execution", task_id=task_id, run_id=run_id, agent_name="ResearcherAgent"
        ):
            # Build research queries from subtasks
            queries = []
            for st in state.subtasks or []:
                if st.get("assigned_agent") == AgentRole.RESEARCHER.value:
                    queries.append(st.get("description", ""))

            if not queries and state.input:
                queries = [state.input]

            all_results: List[ResearchResult] = []
            for q in queries[:3]:  # Limit to 3 queries
                results = await self.researcher.research(q, task_id, run_id)
                all_results.extend(results)

        state.research_results = [r.model_dump() for r in all_results]

        # Review research
        review = await self.reviewer.review_research([ResearchResult(**r) for r in all_results], task_id)
        state.review_results = state.review_results or []
        state.review_results.append(review.model_dump())

        if review.final_recommendation == "revise":
            retry_count = state.retry_count or 0
            if retry_count < self.max_research_retries:
                state.retry_count = retry_count + 1
                state.errors = state.errors or []
                state.errors.append(
                    {
                        "node": "Researcher",
                        "type": "research_revision",
                        "message": "; ".join(review.identified_issues),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )
                return Command(update=state.model_dump(), goto=RESEARCHER_NODE)

        return Command(update=state.model_dump(), goto=CODER_NODE)

    async def _coder_node(self, state: AgentState) -> Command:
        task_id = state.task_id
        run_id = state.run_id

        # Find coding subtasks
        code_subtasks = [
            st for st in (state.subtasks or []) if st.get("assigned_agent") == AgentRole.CODER.value
        ]

        if not code_subtasks:
            # No coding needed, skip to reviewer
            return Command(update=state.model_dump(), goto=REVIEWER_NODE)

        subtask = code_subtasks[0]
        task_description = subtask.get("description", "")

        # Build research context
        research_context = "\n".join(r.get("content", "") for r in (state.research_results or []))

        with self.tracer.span("coder_execution", task_id=task_id, run_id=run_id, agent_name="CoderAgent"):
            code = await self.coder.generate_code(task_description, research_context, task_id)
            state.generated_code = code

            # Execute in sandbox
            exec_result = await self.coder.execute_code(code, state)
            state.sandbox_execution_results = state.sandbox_execution_results or []
            state.sandbox_execution_results.append(exec_result)

        # Review code
        review = await self.reviewer.review_code(code, exec_result, task_id)
        state.review_results = state.review_results or []
        state.review_results.append(review.model_dump())

        if review.final_recommendation == "revise":
            retry_count = state.retry_count or 0
            if retry_count < self.max_code_retries:
                state.retry_count = retry_count + 1
                state.errors = state.errors or []
                state.errors.append(
                    {
                        "node": "Coder",
                        "type": "code_revision",
                        "message": "; ".join(review.identified_issues),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )
                return Command(update=state.model_dump(), goto=CODER_NODE)

        # Check if any subtask requires approval
        for st in state.subtasks or []:
            if st.get("requires_approval") and st.get("status") != ExecutionStatus.COMPLETED.value:
                # Create approval request
                approval = ApprovalRequest(
                    id=str(uuid.uuid4()),
                    run_id=run_id,
                    agent_name="CoderAgent",
                    action_type=st.get("required_tools", ["execute_code"])[0]
                    if st.get("required_tools")
                    else "code_execution",
                    action_payload={"code": code, "subtask_id": st.get("id")},
                    target_resource="sandbox",
                    risk_level=RiskLevel(st.get("risk_level", "medium")),
                    reason=f"Subtask {st.get('id')} requires approval: {st.get('description')}",
                    consequences="Executes generated code in sandbox",
                )
                state.approval_requests = state.approval_requests or []
                state.approval_requests.append(approval.model_dump())
                await self.persistence.create_approval_request(approval)

                # Interrupt for human approval
                with self.tracer.span(
                    "human_approval", task_id=task_id, run_id=run_id, agent_name="CoderAgent"
                ):
                    response = interrupt(approval.model_dump())

                decision = ApprovalDecision(response.get("decision", "reject"))
                approval.decision = decision
                approval.decided_at = datetime.now(timezone.utc)
                approval.decided_by = response.get("decided_by", "human")
                approval.decision_reason = response.get("reason", "")
                approval.status = "approved" if decision == ApprovalDecision.APPROVE else "rejected"
                state.approval_results = state.approval_results or []
                state.approval_results.append(approval.model_dump())
                await self.persistence.update_approval_request(approval)

                if decision != ApprovalDecision.APPROVE:
                    state.execution_status = ExecutionStatus.REJECTED.value
                    return Command(update=state.model_dump(), goto=END)

        return Command(update=state.model_dump(), goto=REVIEWER_NODE)

    async def _reviewer_node(self, state: AgentState) -> Command:
        task_id = state.task_id
        run_id = state.run_id

        with self.tracer.span(
            "reviewer_execution", task_id=task_id, run_id=run_id, agent_name="ReviewerAgent"
        ):
            # Final review of all outputs
            all_passed = True
            issues = []

            # Check execution results
            for sr in state.sandbox_execution_results or []:
                if sr.get("error"):
                    all_passed = False
                    issues.append(f"Sandbox error: {sr['error']}")

            # Check for errors
            if state.errors:
                all_passed = False
                issues.extend(e.get("message", "") for e in state.errors)

            if all_passed:
                state.execution_status = ExecutionStatus.COMPLETED.value
                # Build final output
                parts = []
                if state.research_results:
                    parts.append(
                        "Research: "
                        + "; ".join(r.get("content", "")[:200] for r in state.research_results[:2])
                    )
                if state.generated_code:
                    parts.append("Code generated and executed successfully")
                if state.sandbox_execution_results:
                    parts.append(
                        "Sandbox output: " + state.sandbox_execution_results[-1].get("stdout", "")[:500]
                    )
                state.final_output = "\n".join(parts) or "Workflow completed successfully"
            else:
                state.execution_status = ExecutionStatus.FAILED.value
                state.final_output = f"Workflow failed: {'; '.join(issues[:3])}"

        # Persist final state
        await self.persistence.update_workflow_run(
            task_id,
            status=state.execution_status,
            final_result=state.final_output,
            token_usage=state.token_usage,
            estimated_cost=state.estimated_cost,
            error_summary="; ".join(issues[:3]) if issues else None,
        )

        return Command(
            update=state.model_dump(),
            goto=END,
        )

    # ------------------------------------------------------------------
    # Conditional edge routing
    # ------------------------------------------------------------------

    def _route_after_planner(self, state: AgentState) -> str:
        if state.execution_status == ExecutionStatus.FAILED.value:
            return END
        return RESEARCHER_NODE

    def _route_after_researcher(self, state: AgentState) -> str:
        if state.retry_count and state.retry_count >= self.max_research_retries:
            return END
        return CODER_NODE

    def _route_after_coder(self, state: AgentState) -> str:
        # Check if approval is pending
        for ar in state.approval_requests or []:
            if ar.get("status") == "pending":
                return APPROVAL_NODE
        return REVIEWER_NODE

    def _route_after_approval(self, state: AgentState) -> str:
        for ar in state.approval_requests or []:
            if ar.get("status") == "approved":
                return REVIEWER_NODE
            if ar.get("status") == "rejected":
                return END
        return END

    def _route_after_reviewer(self, state: AgentState) -> str:
        if state.execution_status in (ExecutionStatus.COMPLETED.value, ExecutionStatus.FAILED.value):
            return END
        return CODER_NODE

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def build(self):
        graph = StateGraph(AgentState)

        graph.add_node(PLANNER_NODE, self._planner_node)
        graph.add_node(RESEARCHER_NODE, self._researcher_node)
        graph.add_node(CODER_NODE, self._coder_node)
        graph.add_node(REVIEWER_NODE, self._reviewer_node)
        graph.add_node(APPROVAL_NODE, self._approval_node)
        graph.add_node(FINALIZE_NODE, self._finalize_node)

        graph.add_edge(START, PLANNER_NODE)

        graph.add_conditional_edges(
            PLANNER_NODE,
            self._route_after_planner,
            {RESEARCHER_NODE: RESEARCHER_NODE, END: END},
        )

        graph.add_conditional_edges(
            RESEARCHER_NODE,
            self._route_after_researcher,
            {CODER_NODE: CODER_NODE, END: END},
        )

        graph.add_conditional_edges(
            CODER_NODE,
            self._route_after_coder,
            {APPROVAL_NODE: APPROVAL_NODE, REVIEWER_NODE: REVIEWER_NODE},
        )

        graph.add_conditional_edges(
            APPROVAL_NODE,
            self._route_after_approval,
            {REVIEWER_NODE: REVIEWER_NODE, END: END},
        )

        graph.add_conditional_edges(
            REVIEWER_NODE,
            self._route_after_reviewer,
            {CODER_NODE: CODER_NODE, END: END},
        )

        graph.add_edge(FINALIZE_NODE, END)

        self.graph = graph.compile(checkpointer=self.checkpointer, interrupt_after=[APPROVAL_NODE])
        return self.graph

    async def _approval_node(self, state: AgentState) -> Command:
        """Placeholder — approval interrupts are handled inline in _coder_node via langgraph interrupt."""
        return Command(update=state.model_dump(), goto=REVIEWER_NODE)

    async def _finalize_node(self, state: AgentState) -> Command:
        state.execution_logs = state.execution_logs or []
        state.execution_logs.append(
            {
                "event": "workflow_finalized",
                "task_id": state.task_id,
                "run_id": state.run_id,
                "status": state.execution_status,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        return Command(update=state.model_dump(), goto=END)

    # ------------------------------------------------------------------
    # Public run API
    # ------------------------------------------------------------------

    async def run(
        self, user_request: str, thread_id: Optional[str] = None, config: Optional[dict] = None
    ) -> AgentState:
        """Execute the full workflow end-to-end and return the final state."""

        task_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())

        config = config or {}
        if "configurable" not in config:
            config["configurable"] = {}
        config["configurable"]["thread_id"] = thread_id or run_id

        initial_state = AgentState(
            input=user_request,
            task_id=task_id,
            run_id=run_id,
            execution_status=ExecutionStatus.PENDING.value,
        )

        # Start budget tracking
        budget = load_guardrails_from_settings()
        budget.start()

        loop_detector = LoopDetector()

        final_state: Optional[AgentState] = None
        try:
            async for event in self.graph.astream(initial_state, config=config):
                for node_name, node_state in event.items():
                    if isinstance(node_state, AgentState):
                        final_state = node_state
                        # Record loop detection signals
                        if node_state.execution_status:
                            loop_detector.record_state(
                                hashlib.md5(
                                    json.dumps(node_state.execution_status, sort_keys=True).encode()
                                ).hexdigest()
                            )
                        # Budget check
                        budget.record_iteration()
                        guard_result = budget.check_budget()
                        if not guard_result.allowed:
                            final_state.execution_status = ExecutionStatus.TERMINATED.value
                            final_state.final_output = f"Workflow terminated: {guard_result.reason}"
                            final_state.errors = final_state.errors or []
                            final_state.errors.append(
                                {
                                    "node": "Guardrails",
                                    "type": guard_result.termination_reason or "budget_exhausted",
                                    "message": guard_result.reason,
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                }
                            )
                            break

            if final_state is None:
                final_state = initial_state
                final_state.execution_status = ExecutionStatus.FAILED.value
                final_state.final_output = "Workflow produced no final state"

            # Persist agent executions
            await self.persistence.record_agent_executions(run_id, final_state.model_dump())

            return final_state

        except Exception as e:
            logger.exception("Multi-agent workflow execution failed")
            error_state = AgentState(
                input=user_request,
                task_id=task_id,
                run_id=run_id,
                execution_status=ExecutionStatus.FAILED.value,
                errors=[
                    {
                        "node": "Workflow",
                        "type": "execution_error",
                        "message": str(e),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                ],
                final_output=f"Workflow failed: {e}",
            )
            await self.persistence.record_agent_executions(run_id, error_state.model_dump())
            return error_state
