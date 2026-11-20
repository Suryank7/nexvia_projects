# API_DOCUMENTATION.md

## Enterprise RAG Knowledge Platform — API Reference

Base path: `/api/v1`  
Auth: JWT access token in `access_token` HttpOnly cookie (set on login).  
Content-Type: `application/json` unless noted.

---

### Authentication

#### POST /api/v1/auth/login
Authenticate and set access + refresh token cookies.

**Body**
| Field | Type | Required | Description |
|---|---|---|---|
| email | string | Yes | User email |
| password | string | Yes | User password |

**Response** `200`
```json
{ "access_token": "<jwt>" }
```
Cookies set: `access_token`, `refresh_token` (HttpOnly).

Rate limit: 10/minute.

#### POST /api/v1/auth/refresh
Rotate refresh token, issue new access token.

**Cookie**: `refresh_token`

**Response** `200`
```json
{ "access_token": "<jwt>" }
```

#### POST /api/v1/auth/logout
Revoke refresh token and clear cookies.

**Cookie**: `refresh_token`

**Response** `204 No Content`

#### GET /api/v1/auth/me
Return current authenticated user.

**Response** `200`
```json
{ "id": "<uuid>", "email": "<string>", "role": "hr\|engineering\|finance\|admin\|demo_admin" }
```

---

### Query

#### POST /api/v1/query
Submit a question. Returns an answer with citations (non-streaming) or SSE stream.

**Body**
| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| query | string | Yes | — | User question (1-1000 chars) |
| stream | boolean | No | false | Stream answer via SSE |
| top_k | integer | No | 5 | Number of source chunks (1-20) |

**Response** `200` (non-stream)
```json
{ "answer": "<string>", "sources": [ { "index": 1, "source": "<string>", "department": "<string>", "chunk_id": "<uuid>", "rerank_score": <float> } ] }
```

**Streaming** (`stream: true`): `text/event-stream` with `data: {token}` events and a final `data: {sources, done: true}`.

RBAC: only returns documents the user's role can access.

---

### Ingestion

#### POST /api/v1/ingest
Upload a document file (PDF/TXT/MD/DOCX, max 20 MB).

**Form fields**
| Field | Type | Required | Description |
|---|---|---|---|
| file | file | Yes | Document file |
| department | string | No | Required for admin; ignored for non-admin |

**Response** `201`
```json
{ "doc_id": "<uuid>", "filename": "<string>", "department": "<string>" }
```

#### POST /api/v1/ingest/url
Ingest a webpage by URL. Extracts visible text and indexes it.

**Form fields**
| Field | Type | Required | Description |
|---|---|---|---|
| url | string | Yes | Webpage URL |
| department | string | No | Required for admin |

**Response** `201`
```json
{ "doc_id": "<uuid>", "source": "<url>", "department": "<string>" }
```

---

### Documents

#### GET /api/v1/documents
List documents visible to the current user's role.

**Query**
| Field | Type | Required | Default |
|---|---|---|---|
| offset | integer | No | 0 |
| limit | integer | No | 50 |

**Response** `200`
```json
{ "documents": [ { "id", "name", "department", "uploaded_at", "chunk_count", "uploaded_by" } ], "total": <int> }
```

---

### Admin

Requires `admin` or `demo_admin` role.

#### GET /api/v1/admin/documents
List all documents (optionally filtered by department).

#### DELETE /api/v1/admin/documents/{document_id}
Delete a document (Qdrant chunks + Postgres row + BM25 rebuild).

#### GET /api/v1/admin/users
List all users.

#### PATCH /api/v1/admin/users/{user_id}/active
Set user active/inactive.

**Body** `{ "is_active": bool }`

#### GET /api/v1/admin/eval/results
List RAGAS evaluation results.

#### POST /api/v1/admin/eval/run
Trigger a background RAGAS evaluation run.

**Response** `202`
```json
{ "status": "started", "started_at": "<iso>" }
```

---

### Feedback

#### POST /api/v1/feedback
Submit feedback on an answer/run.

**Body**
| Field | Type | Required | Description |
|---|---|---|---|
| run_id | uuid | Yes | Eval run ID |
| rating | integer | Yes | 1-5 |
| comment | string | No | Optional comment (max 1000) |

**Response** `201`
```json
{ "id", "run_id", "user_id", "rating", "comment", "created_at" }
```

#### GET /api/v1/feedback
List feedback (optionally filtered by run_id).

**Query**: `run_id`, `offset`, `limit`

#### GET /api/v1/feedback/{feedback_id}
Get a single feedback entry.

---

### Health

#### GET /health
Health check.

**Response** `200`
```json
{ "status": "ok" }
```

---

### Error Responses

| Status | Meaning |
|---|---|
| 400 | Bad request |
| 401 | Unauthenticated |
| 403 | Insufficient role |
| 404 | Not found |
| 413 | File too large |
| 422 | Validation error |
| 429 | Rate limited |
| 500 | Server error |
