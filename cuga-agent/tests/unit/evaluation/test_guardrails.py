"""Guardrail tests: loop detection and budget tracking."""

from __future__ import annotations

import pytest

from cuga.backend.cuga_graph.nodes.multi_agent.guardrails import BudgetTracker, LoopDetector


@pytest.mark.unit
class TestLoopDetector:
    def test_no_loop_on_first_seen_state(self):
        detector = LoopDetector(max_repeats=3)

        detector.record_state("state-a")
        detector.record_state("state-b")
        allowed, reason = detector.detect_loop()

        assert allowed is False
        assert reason is None

    def test_loop_detected_after_repeat(self):
        detector = LoopDetector(max_repeats=3)

        detector.record_state("state-a")
        detector.record_state("state-a")
        detector.record_state("state-a")

        allowed, reason = detector.detect_loop()

        assert allowed is True
        assert reason is not None
        assert "repeated" in reason.lower()

    def test_tool_call_loop(self):
        detector = LoopDetector(max_repeats=3)

        detector.record_tool_call("web_search", "hash-1")
        detector.record_tool_call("web_search", "hash-1")
        detector.record_tool_call("web_search", "hash-1")

        allowed, reason = detector.detect_loop()

        assert allowed is True
        assert reason is not None

    def test_action_loop(self):
        detector = LoopDetector(max_repeats=3)

        detector.record_action("coder", "execute_code", "hash-x")
        detector.record_action("coder", "execute_code", "hash-x")
        detector.record_action("coder", "execute_code", "hash-x")

        allowed, reason = detector.detect_loop()

        assert allowed is True
        assert reason is not None


@pytest.mark.unit
class TestBudgetTracker:
    def test_budget_allows_within_limit(self):
        tracker = BudgetTracker(max_iterations=10, max_cost_usd=100.0)

        tracker.record_tokens(input_tokens=100, output_tokens=50, cost_usd=5.0)
        result = tracker.check_budget()

        assert result.allowed is True
        assert result.budget_exhausted is False

    def test_budget_blocks_over_cost(self):
        tracker = BudgetTracker(max_iterations=10, max_cost_usd=10.0)

        tracker.record_tokens(input_tokens=1000, output_tokens=1000, cost_usd=6.0)
        tracker.record_tokens(input_tokens=1000, output_tokens=1000, cost_usd=6.0)

        result = tracker.check_budget()

        assert result.allowed is False
        assert result.budget_exhausted is True
        assert "cost" in result.reason.lower()

    def test_budget_blocks_over_iterations(self):
        tracker = BudgetTracker(max_iterations=2, max_cost_usd=1000.0)

        tracker.record_iteration()
        tracker.record_iteration()

        result = tracker.check_budget()

        assert result.allowed is False
        assert result.budget_exhausted is True
        assert "iterations" in result.reason.lower()

    def test_budget_totals(self):
        tracker = BudgetTracker(max_iterations=100, max_cost_usd=1000.0)

        tracker.record_tokens(input_tokens=100, output_tokens=50, cost_usd=10.0)
        tracker.record_tokens(input_tokens=200, output_tokens=100, cost_usd=20.0)

        assert tracker.total_input_tokens == 300
        assert tracker.total_output_tokens == 150
        assert tracker.total_cost_usd == 30.0

    def test_consecutive_rejections_block(self):
        tracker = BudgetTracker(max_iterations=100, max_consecutive_rejections=2)

        tracker.record_rejection()
        tracker.record_rejection()

        result = tracker.check_budget()

        assert result.allowed is False
        assert "rejections" in result.reason.lower()

    def test_reset_rejections(self):
        tracker = BudgetTracker(max_iterations=100, max_consecutive_rejections=1)

        tracker.record_rejection()
        result = tracker.check_budget()
        assert result.allowed is False

        tracker.reset_rejections()
        result = tracker.check_budget()
        assert result.allowed is True
