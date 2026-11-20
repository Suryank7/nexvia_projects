"""Agent behavior tests using deterministic fallback (no live LLM required)."""

from __future__ import annotations

import pytest

from cuga.backend.cuga_graph.nodes.multi_agent.schemas import (
    AgentRole,
    ExecutionStatus,
    RiskLevel,
)


@pytest.mark.unit
class TestPlannerAgent:
    def test_planner_produces_valid_plan(self, planner_agent):
        import asyncio

        plan = asyncio.run(planner_agent.plan("Write a hello world script", "task-001", "run-001"))

        assert plan.task_id == "task-001"
        assert plan.objective == "Write a hello world script"
        assert plan.description
        assert isinstance(plan.subtasks, list)
        assert len(plan.subtasks) >= 1
        assert plan.risk_classification in (RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL)
        assert plan.completion_criteria
        assert isinstance(plan.estimated_steps, int)

    def test_planner_subtasks_have_valid_roles(self, planner_agent):
        import asyncio

        plan = asyncio.run(planner_agent.plan("Research and write a report", "task-002", "run-002"))

        for subtask in plan.subtasks:
            assert isinstance(subtask.assigned_agent, AgentRole)
            assert subtask.id
            assert subtask.description
            assert isinstance(subtask.dependencies, list)

    def test_planner_handles_empty_request(self, planner_agent):
        import asyncio

        plan = asyncio.run(planner_agent.plan("", "task-003", "run-003"))

        assert plan.task_id == "task-003"
        assert isinstance(plan.subtasks, list)

    def test_planner_is_deterministic(self, planner_agent):
        import asyncio

        plan_a = asyncio.run(planner_agent.plan("Fixed task", "task-004", "run-004"))
        plan_b = asyncio.run(planner_agent.plan("Fixed task", "task-004", "run-004"))

        assert plan_a.description == plan_b.description
        assert len(plan_a.subtasks) == len(plan_b.subtasks)


@pytest.mark.unit
class TestResearcherAgent:
    def test_researcher_produces_results(self, researcher_agent):
        import asyncio

        results = asyncio.run(researcher_agent.research("secure API authentication", "task-005", "run-005"))

        assert isinstance(results, list)
        assert len(results) >= 1
        for result in results:
            assert result.source
            assert result.content
            assert result.query == "secure API authentication"

    def test_researcher_results_have_confidence(self, researcher_agent):
        import asyncio

        results = asyncio.run(researcher_agent.research("cloud pricing models", "task-006", "run-006"))

        assert len(results) >= 1
        assert results[0].confidence is not None

    def test_researcher_is_deterministic(self, researcher_agent):
        import asyncio

        r_a = asyncio.run(researcher_agent.research("stable query", "task-007", "run-007"))
        r_b = asyncio.run(researcher_agent.research("stable query", "task-007", "run-007"))

        assert len(r_a) == len(r_b)
        assert r_a[0].source == r_b[0].source


@pytest.mark.unit
class TestCoderAgent:
    def test_coder_generates_code(self, coder_agent):
        import asyncio

        code = asyncio.run(coder_agent.generate_code("print hello world", "", "task-008"))

        assert isinstance(code, str)
        assert len(code) > 0
        assert "print" in code.lower() or "hello" in code.lower()

    def test_coder_fallback_is_deterministic(self, coder_agent):
        import asyncio

        code_a = asyncio.run(coder_agent.generate_code("fixed task", "", "task-009"))
        code_b = asyncio.run(coder_agent.generate_code("fixed task", "", "task-009"))

        assert code_a == code_b

    def test_coder_extracts_code_block(self, coder_agent):
        import asyncio

        code = asyncio.run(
            coder_agent.generate_code(
                '```python\nprint("extracted")\n```', "", "task-010"
            )
        )

        assert "print" in code
        assert "```" not in code


@pytest.mark.unit
class TestReviewerAgent:
    def test_reviewer_approves_valid_plan(self, reviewer_agent):
        import asyncio

        from cuga.backend.cuga_graph.nodes.multi_agent.schemas import ExecutionPlan, Subtask

        plan = ExecutionPlan(
            task_id="task-011",
            objective="valid plan",
            description="A valid plan",
            subtasks=[
                Subtask(
                    id="s1",
                    description="do thing",
                    assigned_agent=AgentRole.CODER,
                    dependencies=[],
                )
            ],
            completion_criteria="done",
        )

        result = asyncio.run(reviewer_agent.review_plan(plan, "task-011"))

        assert result.status == ExecutionStatus.COMPLETED
        assert result.final_recommendation == "approve"
        assert len(result.failed_checks) == 0

    def test_reviewer_rejects_plan_with_no_subtasks(self, reviewer_agent):
        import asyncio

        from cuga.backend.cuga_graph.nodes.multi_agent.schemas import ExecutionPlan

        plan = ExecutionPlan(
            task_id="task-012",
            objective="empty plan",
            description="No subtasks",
            subtasks=[],
            completion_criteria="done",
        )

        result = asyncio.run(reviewer_agent.review_plan(plan, "task-012"))

        assert result.status == ExecutionStatus.REJECTED
        assert result.final_recommendation == "revise"
        assert "non_empty_subtasks" in result.failed_checks

    def test_reviewer_approves_clean_code_execution(self, reviewer_agent):
        import asyncio

        result = asyncio.run(
            reviewer_agent.review_code(
                code='print("hello")',
                execution_result={"stdout": "hello", "exit_code": 0, "error": None},
                task_id="task-013",
            )
        )

        assert result.status == ExecutionStatus.COMPLETED
        assert result.final_recommendation == "approve"

    def test_reviewer_rejects_code_with_error(self, reviewer_agent):
        import asyncio

        result = asyncio.run(
            reviewer_agent.review_code(
                code="",
                execution_result={"stdout": "", "exit_code": 1, "error": "boom"},
                task_id="task-014",
            )
        )

        assert result.status == ExecutionStatus.REJECTED
        assert result.final_recommendation == "revise"

    def test_reviewer_reviews_research(self, reviewer_agent):
        import asyncio

        from cuga.backend.cuga_graph.nodes.multi_agent.schemas import ResearchResult

        results = [
            ResearchResult(
                source="web",
                content="finding one",
                query="q",
                confidence="verified",
            )
        ]

        review = asyncio.run(reviewer_agent.review_research(results, "task-015"))

        assert review.status == ExecutionStatus.COMPLETED
        assert review.final_recommendation == "approve"
