-- Migration 001: Multi-agent workflow execution history
-- Additive: creates new tables only, does not modify existing tables.
-- Reversible: DROP TABLE IF EXISTS for each table in reverse order.

-- =====================================================================
-- workflow_runs
-- =====================================================================
CREATE TABLE IF NOT EXISTS workflow_runs (
    id VARCHAR(64) PRIMARY KEY,
    task_id VARCHAR(64) NOT NULL,
    user_request TEXT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    execution_plan JSONB,
    final_result TEXT,
    total_iterations INTEGER DEFAULT 0,
    total_tool_calls INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    estimated_cost DOUBLE PRECISION DEFAULT 0,
    error_summary TEXT
);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_task_id ON workflow_runs(task_id);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_status ON workflow_runs(status);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_started_at ON workflow_runs(started_at);

-- =====================================================================
-- agent_executions
-- =====================================================================
CREATE TABLE IF NOT EXISTS agent_executions (
    id VARCHAR(64) PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL,
    agent_name VARCHAR(64) NOT NULL,
    node_name VARCHAR(64) NOT NULL,
    input_summary TEXT,
    output_summary TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    token_usage JSONB,
    estimated_cost DOUBLE PRECISION DEFAULT 0,
    error_details TEXT
);

CREATE INDEX IF NOT EXISTS idx_agent_executions_run_id ON agent_executions(run_id);
CREATE INDEX IF NOT EXISTS idx_agent_executions_agent_name ON agent_executions(agent_name);
CREATE INDEX IF NOT EXISTS idx_agent_executions_status ON agent_executions(status);

-- =====================================================================
-- approval_history
-- =====================================================================
CREATE TABLE IF NOT EXISTS approval_history (
    id VARCHAR(64) PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL,
    agent_name VARCHAR(64) NOT NULL,
    action_type VARCHAR(64) NOT NULL,
    action_payload JSONB,
    risk_level VARCHAR(16) NOT NULL DEFAULT 'medium',
    approval_status VARCHAR(16) NOT NULL DEFAULT 'pending',
    approved_by VARCHAR(64),
    approval_reason TEXT,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    decided_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_approval_history_run_id ON approval_history(run_id);
CREATE INDEX IF NOT EXISTS idx_approval_history_status ON approval_history(approval_status);
CREATE INDEX IF NOT EXISTS idx_approval_history_agent ON approval_history(agent_name);

-- =====================================================================
-- tool_execution_history
-- =====================================================================
CREATE TABLE IF NOT EXISTS tool_execution_history (
    id VARCHAR(64) PRIMARY KEY,
    run_id VARCHAR(64) NOT NULL,
    agent_name VARCHAR(64) NOT NULL,
    tool_name VARCHAR(128) NOT NULL,
    tool_input_summary TEXT,
    tool_output_summary TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    execution_duration DOUBLE PRECISION DEFAULT 0,
    error_details TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tool_exec_history_run_id ON tool_execution_history(run_id);
CREATE INDEX IF NOT EXISTS idx_tool_exec_history_tool_name ON tool_execution_history(tool_name);
CREATE INDEX IF NOT EXISTS idx_tool_exec_history_status ON tool_execution_history(status);

-- =====================================================================
-- Reversal (down migration)
-- =====================================================================
-- DROP TABLE IF EXISTS tool_execution_history;
-- DROP TABLE IF EXISTS approval_history;
-- DROP TABLE IF EXISTS agent_executions;
-- DROP TABLE IF EXISTS workflow_runs;
