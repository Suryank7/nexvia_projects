"""Schema validation tests for multi-agent workflow data models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cuga.backend.cuga_graph.nodes.multi_agent.schemas import (
    AgentRole,
    ApprovalDecision,
    ExecutionPlan,
    ExecutionStatus,
    ResearchResult,
    ReviewOutput,
    RiskLevel,
    Subtask,
)


@pytest.mark.unit
class TestSubtaskSchema:
    def test_valid_subtask(self):
        st = Subtask(
            id="s1",
            description="do work",
            assigned_agent=AgentRole.CODER,
            dependencies=[],
            required_tools=["execute_code"],
            risk_level=RiskLevel.MEDIUM,
            requires_approval=True,
        )

        assert st.id == "s1"
        assert st.status == ExecutionStatus.PENDING
        assert st.retry_count == 0

    def test_subtask_missing_required_fields(self):
        with pytest.raises(ValidationError):
            Subtask(id="s1")

    def test_subtask_invalid_agent_role(self):
        with pytest.raises(ValidationError):
            Subtask(
                id="s1",
                description="d",
                assigned_agent="not_a_role",
            )


@pytest.mark.unit
class TestExecutionPlanSchema:
    def test_valid_plan(self):
        plan = ExecutionPlan(
            task_id="t1",
            objective="obj",
            description="desc",
            completion_criteria="done",
        )

        assert plan.task_id == "t1"
        assert plan.risk_classification == RiskLevel.LOW
        assert plan.subtasks == []

    def test_plan_with_subtasks(self):
        plan = ExecutionPlan(
            task_id="t2",
            objective="obj",
            description="desc",
            subtasks=[
                Subtask(id="s1", description="d1", assigned_agent=AgentRole.RESEARCHER),
                Subtask(id="s2", description="d2", assigned_agent=AgentRole.CODER, dependencies=["s1"]),
            ],
            dependencies={"s2": ["s1"]},
            completion_criteria="all done",
        )

        assert len(plan.subtasks) == 2
        assert plan.estimated_steps >= 0

    def test_plan_missing_required(self):
        with pytest.raises(ValidationError):
            ExecutionPlan(task_id="t3")


@pytest.mark.unit
class TestResearchResultSchema:
    def test_valid_research_result(self):
        result = ResearchResult(
            source="web",
            content="finding",
            query="q",
        )

        assert result.source == "web"
        assert result.content == "finding"
        assert result.confidence is None

    def test_research_result_missing_required(self):
        with pytest.raises(ValidationError):
            ResearchResult(source="web")


@pytest.mark.unit
class TestReviewOutputSchema:
    def test_approved_review(self):
        review = ReviewOutput(
            status=ExecutionStatus.COMPLETED,
            final_recommendation="approve",
        )

        assert review.status == ExecutionStatus.COMPLETED
        assert review.final_recommendation == "approve"

    def test_review_missing_status(self):
        with pytest.raises(ValidationError):
            ReviewOutput(final_recommendation="approve")


@pytest.mark.unit
class TestEnums:
    def test_risk_level_values(self):
        assert {r.value for r in RiskLevel} == {"low", "medium", "high", "critical"}

    def test_approval_decision_values(self):
        assert {d.value for d in ApprovalDecision} == {
            "approve",
            "reject",
            "request_modification",
        }

    def test_agent_role_values(self):
        assert {r.value for r in AgentRole} == {"planner", "researcher", "coder", "reviewer"}

    def test_execution_status_values(self):
        assert ExecutionStatus.COMPLETED.value == "completed"
        assert ExecutionStatus.WAITING_FOR_APPROVAL.value == "waiting_for_approval"
