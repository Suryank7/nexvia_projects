# Multi-Agent Workflow API

The Multi-Agent Autonomous Workflow (MAW) API is mounted at `/api/workflow` on
the CUGA FastAPI server (`src/cuga/backend/server/main.py`). All endpoints are
defined in `src/cuga/backend/server/workflow_routes/__init__.py`.

## Base path

`/api/workflow`

## Endpoints

### POST /run

Submit a task to the multi-agent autonomous workflow. The Planner creates a
plan, Researcher gathers information, Coder generates and executes code in the
sandbox, Reviewer validates, and the workflow produces a final result. Risky
actions pause for approval.

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `query` | string | Yes | The user's task/objective |
| `thread_id` | string | No | Optional conversation thread ID |

**Response** (`200`)

| Field | Type | Description |
|---|---|---|
| `task_id` | string | Unique workflow task identifier |
| `run_id` | string | Workflow run identifier |
| `status` | string | Current execution status |
| `message` | string | Human-readable status message |

**Example**

```bash
curl -X POST http://localhost:7860/api/workflow/run \
  -H "Content-Type: application/json" \
  -d '{"query": "Write a Python script that calculates compound interest", "thread_id": "thread-123"}'
```

### GET /state/{task_id}

View the current execution state and progress for a task.

**Path parameters**

| Field | Type | Description |
|---|---|---|
| `task_id` | string | The task identifier returned by POST /run |

**Response** (`200`): the persisted workflow run record (`JSONResponse`).

**Response** (`404`): task not found.

### POST /approve

Approve, reject, or request modification of a pending approval request.

**Request body**

| Field | Type | Required | Description |
|---|---|---|---|
| `request_id` | string | Yes | The approval request identifier |
| `decision` | string | Yes | `approve`, `reject`, or `request_modification` |
| `decided_by` | string | No | Who made the decision (default `"human"`) |
| `reason` | string | No | Optional reason for the decision |

**Response** (`200`)

| Field | Type | Description |
|---|---|---|
| `ok` | bool | `true` |
| `request_id` | string | The approval request identifier |
| `decision` | string | The decision applied |
| `message` | string | Confirmation message |

**Response** (`404`): pending approval not found.

**Response** (`400`): invalid decision value.

### GET /history

List workflow execution history.

**Query parameters**

| Field | Type | Required | Description |
|---|---|---|---|
| `limit` | integer | No | Max runs to return (default `50`) |

**Response** (`200`)

| Field | Type | Description |
|---|---|---|
| `runs` | array | List of workflow run records |
| `count` | integer | Number of runs returned |

### GET /history/{task_id}

Get a single workflow run by task ID, including its approval history.

**Path parameters**

| Field | Type | Description |
|---|---|---|
| `task_id` | string | The task identifier |

**Response** (`200`)

| Field | Type | Description |
|---|---|---|
| `run` | object | The workflow run record |
| `approvals` | array | Approval history for the run |

**Response** (`404`): task not found.

### GET /approvals/{run_id}

Get approval history for a specific run.

**Path parameters**

| Field | Type | Description |
|---|---|---|
| `run_id` | string | The workflow run identifier |

**Response** (`200`)

| Field | Type | Description |
|---|---|---|
| `run_id` | string | The workflow run identifier |
| `approvals` | array | List of approval records |

### GET /plan/{task_id}

Get the execution plan for a task.

**Path parameters**

| Field | Type | Description |
|---|---|---|
| `task_id` | string | The task identifier |

**Response** (`200`)

| Field | Type | Description |
|---|---|---|
| `task_id` | string | The task identifier |
| `execution_plan` | object | The planner's execution plan |
| `status` | string | Current run status |

**Response** (`404`): task not found.

## Errors

| Status | Meaning |
|---|---|
| `400` | Bad request (missing query, invalid decision) |
| `404` | Task or approval not found |
| `500` | Workflow execution failure |

## Mounting

The router is registered in `src/cuga/backend/server/main.py`:

```python
from cuga.backend.server import workflow_routes
app.include_router(workflow_routes.router)
```

The router prefix is `/api/workflow` with tag `multi-agent-workflow`.
