"""Validation tests for the 20-task multi-agent evaluation dataset."""

from __future__ import annotations

import pytest

from cuga.backend.cuga_graph.nodes.multi_agent.schemas import AgentRole, RiskLevel


@pytest.mark.unit
class TestEvaluationDataset:
    """The evaluation dataset must be well-formed and cover all agent roles."""

    def test_dataset_has_exactly_20_tasks(self, evaluation_dataset):
        assert len(evaluation_dataset) == 20

    def test_task_ids_are_unique(self, evaluation_dataset):
        ids = [t["id"] for t in evaluation_dataset]
        assert len(ids) == len(set(ids))

    def test_each_task_has_required_fields(self, evaluation_dataset):
        for task in evaluation_dataset:
            assert "id" in task and task["id"]
            assert "query" in task and task["query"].strip()
            assert "category" in task and task["category"]
            assert "expected_risk" in task

    def test_task_categories_are_valid(self, evaluation_dataset):
        valid = {"research", "coding"}
        for task in evaluation_dataset:
            assert task["category"] in valid

    def test_expected_risk_levels_are_valid(self, evaluation_dataset):
        valid = {r.value for r in RiskLevel}
        for task in evaluation_dataset:
            assert task["expected_risk"] in valid

    def test_dataset_covers_both_categories(self, evaluation_dataset):
        categories = {t["category"] for t in evaluation_dataset}
        assert "research" in categories
        assert "coding" in categories

    def test_task_ids_are_sequential(self, evaluation_dataset):
        ids = [t["id"] for t in evaluation_dataset]
        expected = [f"task-{i:03d}" for i in range(1, 21)]
        assert ids == expected

    def test_agent_role_coverage(self):
        """All four agent roles must be represented in the schema."""
        roles = {r.value for r in AgentRole}
        assert roles == {"planner", "researcher", "coder", "reviewer"}
