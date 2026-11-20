"""Evaluation report generator: writes a summary report after tests run."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cuga.backend.cuga_graph.nodes.multi_agent.schemas import AgentRole, RiskLevel


REPORT_PATH = Path("tests/unit/evaluation/evaluation_report.json")


@pytest.mark.unit
def test_generate_evaluation_report(evaluation_dataset):
    """Generate an evaluation report summarizing dataset coverage and agent roles."""
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "suite": "multi-agent-autonomous-workflow",
        "task_count": len(evaluation_dataset),
        "category_distribution": {
            cat: sum(1 for t in evaluation_dataset if t["category"] == cat)
            for cat in {"research", "coding"}
        },
        "risk_distribution": {
            level: sum(1 for t in evaluation_dataset if t["expected_risk"] == level)
            for level in {r.value for r in RiskLevel}
        },
        "agent_roles": [r.value for r in AgentRole],
        "task_ids": [t["id"] for t in evaluation_dataset],
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2))

    assert REPORT_PATH.exists()
    assert report["task_count"] == 20
    assert report["category_distribution"]["research"] > 0
    assert report["category_distribution"]["coding"] > 0
