"""Fixtures for the multi-agent workflow evaluation test suite."""

from __future__ import annotations

import pytest

from cuga.backend.cuga_graph.nodes.multi_agent.agents import (
    CoderAgent,
    PlannerAgent,
    ResearcherAgent,
    ReviewerAgent,
)


EVALUATION_DATASET = [
    {"id": "task-001", "query": "Summarize the key findings of the latest quarterly sales report.", "category": "research", "expected_risk": "low"},
    {"id": "task-002", "query": "Write a Python script that calculates compound interest over 10 years.", "category": "coding", "expected_risk": "low"},
    {"id": "task-003", "query": "Research current best practices for secure API authentication.", "category": "research", "expected_risk": "low"},
    {"id": "task-004", "query": "Generate a unit test suite for a user registration endpoint.", "category": "coding", "expected_risk": "low"},
    {"id": "task-005", "query": "Analyze website traffic trends from the provided access logs.", "category": "research", "expected_risk": "low"},
    {"id": "task-006", "query": "Create a CSV exporter that writes query results to a local file.", "category": "coding", "expected_risk": "medium"},
    {"id": "task-007", "query": "Look up the public holiday calendar for the United States in 2027.", "category": "research", "expected_risk": "low"},
    {"id": "task-008", "query": "Write a data validation function for JSON schema compliance.", "category": "coding", "expected_risk": "low"},
    {"id": "task-009", "query": "Research competitor pricing models for SaaS analytics platforms.", "category": "research", "expected_risk": "low"},
    {"id": "task-010", "query": "Generate a Python module that parses and normalizes phone numbers.", "category": "coding", "expected_risk": "low"},
    {"id": "task-011", "query": "Summarize the main arguments in the climate policy white paper.", "category": "research", "expected_risk": "low"},
    {"id": "task-012", "query": "Create a backup script that copies important documents to an archive folder.", "category": "coding", "expected_risk": "medium"},
    {"id": "task-013", "query": "Investigate recent changes in remote work legislation across the EU.", "category": "research", "expected_risk": "low"},
    {"id": "task-014", "query": "Write a log parser that extracts error entries and groups them by severity.", "category": "coding", "expected_risk": "low"},
    {"id": "task-015", "query": "Research open-source alternatives to commercial vector databases.", "category": "research", "expected_risk": "low"},
    {"id": "task-016", "query": "Generate a configuration file validator for YAML-based app settings.", "category": "coding", "expected_risk": "low"},
    {"id": "task-017", "query": "Look up shipping carrier rate tables for domestic parcel delivery.", "category": "research", "expected_risk": "low"},
    {"id": "task-018", "query": "Write a Python class that wraps a REST API with retry and timeout handling.", "category": "coding", "expected_risk": "medium"},
    {"id": "task-019", "query": "Summarize customer feedback themes from the support ticket dataset.", "category": "research", "expected_risk": "low"},
    {"id": "task-020", "query": "Create a health-check script that pings multiple endpoints and reports status.", "category": "coding", "expected_risk": "medium"},
]


@pytest.fixture
def evaluation_dataset():
    return list(EVALUATION_DATASET)


@pytest.fixture
def planner_agent():
    return PlannerAgent(model=None)


@pytest.fixture
def researcher_agent():
    return ResearcherAgent(model=None)


@pytest.fixture
def coder_agent():
    return CoderAgent(model=None)


@pytest.fixture
def reviewer_agent():
    return ReviewerAgent(model=None)
