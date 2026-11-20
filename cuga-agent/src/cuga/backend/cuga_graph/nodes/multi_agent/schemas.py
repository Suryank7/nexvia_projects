"""Shared Pydantic schemas for the multi-agent autonomous workflow."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ApprovalDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_MODIFICATION = "request_modification"


class AgentRole(str, Enum):
    PLANNER = "planner"
    RESEARCHER = "researcher"
    CODER = "coder"
    REVIEWER = "reviewer"


class ExecutionStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    REJECTED = "rejected"
    TERMINATED = "terminated"


class Subtask(BaseModel):
    """A single executable unit within an execution plan."""

    id: str = Field(..., description="Unique subtask identifier")
    description: str = Field(..., description="Human-readable subtask description")
    assigned_agent: AgentRole = Field(..., description="Agent role responsible")
    dependencies: List[str] = Field(default_factory=list, description="Subtask IDs this depends on")
    required_tools: List[str] = Field(default_factory=list, description="Tool names needed")
    risk_level: RiskLevel = Field(default=RiskLevel.LOW, description="Risk classification")
    requires_approval: bool = Field(default=False, description="Needs human approval before execution")
    status: ExecutionStatus = Field(default=ExecutionStatus.PENDING)
    result: Optional[str] = Field(None, description="Subtask execution result")
    error: Optional[str] = Field(None, description="Error message if failed")
    retry_count: int = Field(default=0)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class ExecutionPlan(BaseModel):
    """Structured execution plan produced by the Planner agent."""

    task_id: str = Field(..., description="Unique workflow task identifier")
    objective: str = Field(..., description="Original user request")
    description: str = Field(..., description="Plan summary")
    subtasks: List[Subtask] = Field(default_factory=list)
    dependencies: Dict[str, List[str]] = Field(
        default_factory=dict, description="Subtask ID -> dependency IDs"
    )
    assigned_agents: Dict[str, AgentRole] = Field(
        default_factory=dict, description="Subtask ID -> agent role"
    )
    required_tools: List[str] = Field(default_factory=list, description="All tools referenced by the plan")
    risk_classification: RiskLevel = Field(default=RiskLevel.LOW, description="Overall plan risk")
    approval_requirements: List[str] = Field(default_factory=list, description="Subtask IDs needing approval")
    completion_criteria: str = Field(..., description="Criteria for considering the plan complete")
    estimated_steps: int = Field(default=0, description="Estimated number of execution steps")
    created_at: Optional[datetime] = None


class ResearchResult(BaseModel):
    """Structured research finding from the Researcher agent."""

    source: str = Field(..., description="Source name (web, mcp, file, browser)")
    content: str = Field(..., description="Retrieved content or summary")
    source_url: Optional[str] = Field(None, description="Source URL or file reference")
    retrieval_timestamp: Optional[datetime] = Field(default_factory=datetime.now)
    confidence: Optional[str] = Field(None, description="Confidence or verification status")
    query: str = Field(..., description="Original research query")


class ReviewOutput(BaseModel):
    """Structured review output from the Reviewer agent."""

    status: ExecutionStatus = Field(..., description="Review status")
    validation_results: List[str] = Field(default_factory=list, description="Passed checks")
    failed_checks: List[str] = Field(default_factory=list, description="Failed checks")
    identified_issues: List[str] = Field(default_factory=list, description="Issues found")
    required_corrections: List[str] = Field(default_factory=list, description="Corrections needed")
    final_recommendation: str = Field(..., description="approve | revise | reject")
    evidence: List[str] = Field(default_factory=list, description="Evidence supporting recommendation")
    target_agent: Optional[AgentRole] = Field(None, description="Agent to receive corrections")


class ApprovalRequest(BaseModel):
    """Human-in-the-loop approval request."""

    id: str = Field(..., description="Unique approval request identifier")
    run_id: str = Field(..., description="Workflow run identifier")
    agent_name: str = Field(..., description="Agent requesting approval")
    action_type: str = Field(..., description="Type of action (email, file_write, delete, api_call, etc.)")
    action_payload: Dict[str, Any] = Field(
        default_factory=dict, description="Exact parameters for the action"
    )
    target_resource: Optional[str] = Field(None, description="Target resource being acted on")
    risk_level: RiskLevel = Field(..., description="Risk classification")
    reason: str = Field(..., description="Why approval is necessary")
    consequences: Optional[str] = Field(None, description="Potential consequences of the action")
    status: str = Field(default="pending", description="pending | approved | rejected | timed_out")
    requested_by: str = Field(..., description="Agent name")
    requested_at: Optional[datetime] = Field(default_factory=datetime.now)
    decided_at: Optional[datetime] = None
    decided_by: Optional[str] = None
    decision: Optional[ApprovalDecision] = None
    decision_reason: Optional[str] = None


class TokenUsage(BaseModel):
    """Token usage tracking."""

    input_tokens: int = Field(default=0)
    output_tokens: int = Field(default=0)
    total_tokens: int = Field(default=0)
    estimated_cost: float = Field(default=0.0)
    model_name: Optional[str] = None


class GuardrailResult(BaseModel):
    """Result of guardrail evaluation."""

    allowed: bool = Field(..., description="Whether execution may continue")
    reason: Optional[str] = Field(None, description="Termination reason if not allowed")
    termination_reason: Optional[str] = None
    retry_count: int = Field(default=0)
    loop_detected: bool = Field(default=False)
    budget_exhausted: bool = Field(default=False)
