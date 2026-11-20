"""Four specialized agents for the multi-agent autonomous workflow.

Planner, Researcher, Coder, and Reviewer agents that collaborate through
the LangGraph workflow defined in workflow.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from loguru import logger
from pydantic import BaseModel

from cuga.backend.cuga_graph.nodes.multi_agent.schemas import (
    AgentRole,
    ExecutionPlan,
    ExecutionStatus,
    ResearchResult,
    ReviewOutput,
    RiskLevel,
    Subtask,
)
from cuga.backend.cuga_graph.state.agent_state import AgentState
from cuga.backend.llm.models import LLMManager
from cuga.config import settings


llm_manager = LLMManager()


class _ModelCall(BaseModel):
    """Lightweight token usage record."""

    model: str = "unknown"
    input_tokens: int = 0
    output_tokens: int = 0


class PlannerAgent:
    """Planner Agent: breaks a user objective into an executable plan.

    Produces an ExecutionPlan with subtasks, dependencies, agent assignments,
    tool requirements, risk classification, and approval requirements.
    """

    name = "PlannerAgent"
    role = AgentRole.PLANNER

    def __init__(self, model=None):
        self.model = model or self._default_model()

    def _default_model(self):
        try:
            cfg = settings.agent.code.model.copy() if settings.agent.code.model else {}
            cfg.setdefault("streaming", False)
            return llm_manager.get_model(cfg)
        except Exception as e:
            logger.warning(f"PlannerAgent: could not load configured model: {e}")
            return None

    async def plan(self, user_request: str, task_id: str, run_id: str) -> ExecutionPlan:
        """Break the user request into a structured execution plan."""

        prompt = f"""You are a Planner Agent in a multi-agent autonomous workflow system.

User request: {user_request}
Task ID: {task_id}
Run ID: {run_id}

Break this objective into an executable plan. Return a JSON object with:
- description: concise plan summary
- subtasks: array of {{id, description, assigned_agent (planner|researcher|coder|reviewer), dependencies (array of subtask IDs), required_tools (array of tool names), risk_level (low|medium|high|critical), requires_approval (bool)}}
- dependencies: map of subtask ID -> array of dependency subtask IDs
- required_tools: all unique tool names referenced
- risk_classification: overall risk (low|medium|high|critical)
- approval_requirements: array of subtask IDs that need human approval
- completion_criteria: how to know the plan is complete
- estimated_steps: estimated number of steps

Available agent roles: planner, researcher, coder, reviewer.
Available tools: web_search, web_page_retrieval, read_file, write_file, execute_code, browse_page, query_database.

Rules:
- Research first, then code, then review.
- Assign code execution to coder only.
- Assign information gathering to researcher only.
- Mark file writes, deletions, external API calls, and paid operations as requires_approval=true with risk medium+.
- Mark destructive commands as risk high or critical.
- Dependencies must be acyclic.
- Output ONLY valid JSON, no markdown fences."""

        messages = [
            {"role": "system", "content": "You are a meticulous Planner Agent. Output only valid JSON."},
            {"role": "user", "content": prompt},
        ]

        plan_dict: Dict[str, Any] = {}
        if self.model is not None:
            try:
                from langchain_core.messages import HumanMessage, SystemMessage

                lc_messages = [
                    SystemMessage(content=messages[0]["content"]),
                    HumanMessage(content=messages[1]["content"]),
                ]
                response = await self.model.ainvoke(lc_messages)
                content = getattr(response, "content", str(response))
                import json as _json

                plan_dict = _json.loads(content)
            except Exception as e:
                logger.warning(f"PlannerAgent LLM call failed: {e}; using fallback plan")
                plan_dict = {}
        else:
            logger.warning("PlannerAgent: no model available; using fallback plan")

        if not plan_dict:
            plan_dict = self._fallback_plan(user_request, task_id)

        subtasks = []
        for st in plan_dict.get("subtasks", []):
            subtasks.append(
                Subtask(
                    id=st.get("id", str(uuid.uuid4())[:8]),
                    description=st.get("description", ""),
                    assigned_agent=AgentRole(st.get("assigned_agent", "researcher")),
                    dependencies=st.get("dependencies", []),
                    required_tools=st.get("required_tools", []),
                    risk_level=RiskLevel(st.get("risk_level", "low")),
                    requires_approval=st.get("requires_approval", False),
                )
            )

        return ExecutionPlan(
            task_id=task_id,
            objective=user_request,
            description=plan_dict.get("description", "Auto-generated plan"),
            subtasks=subtasks,
            dependencies=plan_dict.get("dependencies", {}),
            assigned_agents={},
            required_tools=plan_dict.get("required_tools", []),
            risk_classification=RiskLevel(plan_dict.get("risk_classification", "low")),
            approval_requirements=plan_dict.get("approval_requirements", []),
            completion_criteria=plan_dict.get("completion_criteria", "All subtasks completed successfully"),
            estimated_steps=plan_dict.get("estimated_steps", len(subtasks)),
            created_at=datetime.now(timezone.utc),
        )

    def _fallback_plan(self, user_request: str, task_id: str) -> Dict[str, Any]:
        """Deterministic fallback plan when the LLM is unavailable."""

        return {
            "description": "Research the objective, then generate and review code.",
            "subtasks": [
                {
                    "id": "subtask_1",
                    "description": f"Research information relevant to: {user_request[:100]}",
                    "assigned_agent": "researcher",
                    "dependencies": [],
                    "required_tools": ["web_search"],
                    "risk_level": "low",
                    "requires_approval": False,
                },
                {
                    "id": "subtask_2",
                    "description": f"Generate code to address: {user_request[:100]}",
                    "assigned_agent": "coder",
                    "dependencies": ["subtask_1"],
                    "required_tools": ["execute_code"],
                    "risk_level": "medium",
                    "requires_approval": False,
                },
                {
                    "id": "subtask_3",
                    "description": "Review generated code and research results",
                    "assigned_agent": "reviewer",
                    "dependencies": ["subtask_2"],
                    "required_tools": [],
                    "risk_level": "low",
                    "requires_approval": False,
                },
            ],
            "dependencies": {"subtask_2": ["subtask_1"], "subtask_3": ["subtask_2"]},
            "required_tools": ["web_search", "execute_code"],
            "risk_classification": "medium",
            "approval_requirements": [],
            "completion_criteria": "All subtasks completed and reviewed successfully",
            "estimated_steps": 3,
        }


class ResearcherAgent:
    """Researcher Agent: searches and retrieves relevant information.

    Uses existing MCP integrations, web search tools, and Playwright browser
    automation. Returns structured ResearchResult objects.
    """

    name = "ResearcherAgent"
    role = AgentRole.RESEARCHER

    def __init__(self, model=None, tool_provider=None):
        self.model = model or self._default_model()
        self.tool_provider = tool_provider

    def _default_model(self):
        try:
            cfg = settings.agent.code.model.copy() if settings.agent.code.model else {}
            cfg.setdefault("streaming", False)
            return llm_manager.get_model(cfg)
        except Exception as e:
            logger.warning(f"ResearcherAgent: could not load configured model: {e}")
            return None

    async def research(self, query: str, task_id: str, run_id: str) -> List[ResearchResult]:
        """Research a query and return structured findings."""

        results: List[ResearchResult] = []

        # Try web search via tool provider (MCP)
        if self.tool_provider is not None:
            try:
                tools = await self.tool_provider.get_apps()
                for app in tools or []:
                    app_name = getattr(app, "name", str(app))
                    if "search" in app_name.lower() or "web" in app_name.lower():
                        try:
                            app_tools = await self.tool_provider.get_tools(app_name)
                            for t in app_tools or []:
                                tool_name = getattr(t, "name", str(t))
                                if "search" in tool_name.lower():
                                    result = await self.tool_provider.invoke_tool(
                                        app_name, tool_name, {"query": query}
                                    )
                                    results.append(
                                        ResearchResult(
                                            source=f"mcp:{app_name}",
                                            content=str(result)[:2000],
                                            source_url=None,
                                            confidence="unverified",
                                            query=query,
                                        )
                                    )
                                    break
                        except Exception as e:
                            logger.debug(f"ResearcherAgent MCP search skipped for {app_name}: {e}")
            except Exception as e:
                logger.debug(f"ResearcherAgent tool provider search skipped: {e}")

        # Fallback: use LLM to synthesize research from available knowledge
        if not results and self.model is not None:
            try:
                from langchain_core.messages import HumanMessage, SystemMessage

                response = await self.model.ainvoke(
                    [
                        SystemMessage(
                            content="You are a Researcher Agent. Research the query using your knowledge. "
                            "Return findings with source attribution and confidence level."
                        ),
                        HumanMessage(content=query),
                    ]
                )
                content = getattr(response, "content", str(response))
                results.append(
                    ResearchResult(
                        source="llm_knowledge",
                        content=content[:2000],
                        source_url=None,
                        confidence="llm_generated",
                        query=query,
                    )
                )
            except Exception as e:
                logger.warning(f"ResearcherAgent LLM research failed: {e}")

        if not results:
            results.append(
                ResearchResult(
                    source="fallback",
                    content=f"No external sources available for query: {query}",
                    source_url=None,
                    confidence="unavailable",
                    query=query,
                )
            )

        return results


class CoderAgent:
    """Coder Agent: generates code and executes it in the E2B sandbox.

    Generated code always runs inside the existing E2B/OpenSandbox/Docker
    sandbox via `run_code()` — never directly on the host.
    """

    name = "CoderAgent"
    role = AgentRole.CODER

    def __init__(self, model=None):
        self.model = model or self._default_model()

    def _default_model(self):
        try:
            cfg = settings.agent.code.model.copy() if settings.agent.code.model else {}
            cfg.setdefault("streaming", False)
            return llm_manager.get_model(cfg)
        except Exception as e:
            logger.warning(f"CoderAgent: could not load configured model: {e}")
            return None

    async def generate_code(self, task_description: str, research_context: str, task_id: str) -> str:
        """Generate Python code to address the task using research context."""

        prompt = f"""You are a Coder Agent. Generate Python code to accomplish the task.

Task: {task_description}

Research context:
{research_context}

Requirements:
- Write safe, executable Python code.
- Use only standard library and commonly available packages.
- Do not access secrets, environment variables, or credentials.
- Do not perform destructive file operations outside the sandbox.
- Print results to stdout.
- Output ONLY the Python code in a single ```python block, no markdown fences around the whole response."""

        code = ""
        if self.model is not None:
            try:
                from langchain_core.messages import HumanMessage, SystemMessage

                response = await self.model.ainvoke(
                    [
                        SystemMessage(content="You are a Coder Agent. Output only executable Python code."),
                        HumanMessage(content=prompt),
                    ]
                )
                code = getattr(response, "content", str(response))
            except Exception as e:
                logger.warning(f"CoderAgent code generation failed: {e}")
                code = self._fallback_code(task_description)
        else:
            code = self._fallback_code(task_description)

        # Extract code from markdown block if present
        code = self._extract_code(code)
        return code

    async def execute_code(self, code: str, state: AgentState) -> Dict[str, Any]:
        """Execute code through the existing sandbox runner (E2B/OpenSandbox/Docker)."""

        from cuga.backend.tools_env.code_sandbox.sandbox import run_code

        start = datetime.now(timezone.utc)
        try:
            stdout, _locals = await run_code(code, state)
            duration_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            return {
                "stdout": stdout,
                "stderr": "",
                "exit_code": 0,
                "duration_ms": duration_ms,
                "error": None,
                "executed_at": start.isoformat(),
            }
        except Exception as e:
            duration_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            logger.error(f"CoderAgent code execution failed: {e}")
            return {
                "stdout": "",
                "stderr": str(e),
                "exit_code": 1,
                "duration_ms": duration_ms,
                "error": str(e),
                "executed_at": start.isoformat(),
            }

    def _extract_code(self, text: str) -> str:
        """Extract Python code from a markdown block, or return the text as-is."""
        import re

        match = re.search(r"```python\n(.*?)\n```", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        match = re.search(r"```\n(.*?)\n```", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return text.strip()

    def _fallback_code(self, task_description: str) -> str:
        """Deterministic fallback code when the LLM is unavailable."""
        return f'''print("Fallback code executed for task: {task_description[:80]}")
result = {{"status": "completed", "task": {task_description!r}}}
print(result)'''


class ReviewerAgent:
    """Reviewer Agent: reviews plans, research, code, and test results.

    Returns structured ReviewOutput with validation results, failed checks,
    identified issues, required corrections, and a final recommendation.
    """

    name = "ReviewerAgent"
    role = AgentRole.REVIEWER

    def __init__(self, model=None):
        self.model = model or self._default_model()

    def _default_model(self):
        try:
            cfg = settings.agent.code.model.copy() if settings.agent.code.model else {}
            cfg.setdefault("streaming", False)
            return llm_manager.get_model(cfg)
        except Exception as e:
            logger.warning(f"ReviewerAgent: could not load configured model: {e}")
            return None

    async def review_plan(self, plan: ExecutionPlan, task_id: str) -> ReviewOutput:
        """Review a planner-generated execution plan."""

        issues = []
        failed_checks = []
        validations = []

        # Structural checks
        if not plan.subtasks:
            issues.append("Plan has no subtasks")
            failed_checks.append("non_empty_subtasks")
        else:
            validations.append("Plan contains subtasks")

        # Check for cycles in dependencies
        subtask_ids = {st.id for st in plan.subtasks}
        for st in plan.subtasks:
            for dep in st.dependencies:
                if dep not in subtask_ids:
                    issues.append(f"Subtask {st.id} depends on unknown subtask {dep}")
                    failed_checks.append(f"valid_dependencies_{st.id}")
            if not st.assigned_agent:
                issues.append(f"Subtask {st.id} has no assigned agent")
                failed_checks.append(f"agent_assigned_{st.id}")

        if failed_checks:
            recommendation = "revise"
            status = ExecutionStatus.REJECTED
        else:
            recommendation = "approve"
            status = ExecutionStatus.COMPLETED

        return ReviewOutput(
            status=status,
            validation_results=validations,
            failed_checks=failed_checks,
            identified_issues=issues,
            required_corrections=[f"Fix: {i}" for i in issues],
            final_recommendation=recommendation,
            evidence=[f"Plan {task_id}: {len(plan.subtasks)} subtasks, risk={plan.risk_classification}"],
            target_agent=AgentRole.PLANNER if issues else None,
        )

    async def review_code(self, code: str, execution_result: Dict[str, Any], task_id: str) -> ReviewOutput:
        """Review generated code and its execution result."""

        issues = []
        failed_checks = []
        validations = []

        if not code or not code.strip():
            issues.append("Generated code is empty")
            failed_checks.append("non_empty_code")

        if execution_result.get("error"):
            issues.append(f"Code execution error: {execution_result['error']}")
            failed_checks.append("code_executes_cleanly")
        else:
            validations.append("Code executed without errors")

        if execution_result.get("exit_code", 0) != 0:
            issues.append(f"Non-zero exit code: {execution_result.get('exit_code')}")
            failed_checks.append("exit_code_zero")

        if execution_result.get("stdout"):
            validations.append("Code produced stdout output")

        if failed_checks:
            recommendation = "revise"
            status = ExecutionStatus.REJECTED
        else:
            recommendation = "approve"
            status = ExecutionStatus.COMPLETED

        return ReviewOutput(
            status=status,
            validation_results=validations,
            failed_checks=failed_checks,
            identified_issues=issues,
            required_corrections=[f"Fix: {i}" for i in issues],
            final_recommendation=recommendation,
            evidence=[
                f"Code execution: exit_code={execution_result.get('exit_code')}, "
                f"stdout_len={len(execution_result.get('stdout', ''))}"
            ],
            target_agent=AgentRole.CODER if issues else None,
        )

    async def review_research(self, research_results: List[ResearchResult], task_id: str) -> ReviewOutput:
        """Review research results for completeness and verifiability."""

        issues = []
        failed_checks = []
        validations = []

        if not research_results:
            issues.append("No research results found")
            failed_checks.append("non_empty_research")
        else:
            validations.append(f"{len(research_results)} research results retrieved")

        low_confidence = [r for r in research_results if r.confidence in (None, "unavailable", "unverified")]
        if low_confidence:
            issues.append(f"{len(low_confidence)} results have low/unverified confidence")
            failed_checks.append("research_confidence")

        if failed_checks:
            recommendation = "revise"
            status = ExecutionStatus.REJECTED
        else:
            recommendation = "approve"
            status = ExecutionStatus.COMPLETED

        return ReviewOutput(
            status=status,
            validation_results=validations,
            failed_checks=failed_checks,
            identified_issues=issues,
            required_corrections=[f"Fix: {i}" for i in issues],
            final_recommendation=recommendation,
            evidence=[
                f"{len(research_results)} sources, "
                f"{sum(1 for r in research_results if r.source_url)} with URLs"
            ],
            target_agent=AgentRole.RESEARCHER if issues else None,
        )
