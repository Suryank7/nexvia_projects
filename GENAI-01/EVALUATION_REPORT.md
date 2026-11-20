# EVALUATION_REPORT.md

## Enterprise RAG Knowledge Platform — Evaluation Report

### Evaluation Methodology

The platform uses **RAGAS** (Retrieval-Augmented Generation Assessment) to evaluate answer quality against retrieved context and ground truth. Evaluation runs:

1. Load test questions from `backend/eval/datasets/test_dataset.json`.
2. For each question, run hybrid retrieval (dense + sparse + RRF) scoped to the question's role, rerank, and generate an answer.
3. Run RAGAS metrics: faithfulness, answer_relevancy, context_recall, context_precision.
4. Save results as CSV to `backend/eval/results/` and persist scores to PostgreSQL (`eval_results` table).
5. Admin can trigger a run via `POST /api/v1/admin/eval/run` and view results in the admin panel.

### Test Task Distribution

| Category | Role | Number of Questions |
|---|---|---|
| HR (leave, benefits, reviews, conduct, hiring) | hr | 19 |
| Engineering (deployment, incidents, API, security, architecture) | engineering | 17 |
| Finance (expenses, budget, audit, procurement, reporting) | finance | 14 |
| **Total** | | **50** |

Each question includes a question, role, and ground_truth answer grounded in the department data files under `backend/data/{hr,engineering,finance}/`.

### Required Environment

Evaluation requires:
- PostgreSQL running with the platform schema initialized
- Qdrant running with ingested documents
- OpenAI API key (`OPENAI_API_KEY`)
- LangSmith optional for tracing

External services (Qdrant, PostgreSQL, OpenAI) must be available for a live evaluation run. Offline mode is not supported for RAGAS because it requires live retrieval + generation.

### How to Run

```bash
# 1. Start infrastructure (PostgreSQL + Qdrant)
cd backend
docker compose up postgres qdrant -d   # if docker compose available

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure .env (copy .env.example, fill in values)
cp .env.example .env
# Edit .env with your database, Qdrant, and OpenAI settings

# 4. Ingest documents
python scripts/run_ingestion.py --department hr --dir data/hr/ --uploader-id <admin-uuid>
python scripts/run_ingestion.py --department engineering --dir data/engineering/ --uploader-id <admin-uuid>
python scripts/run_ingestion.py --department finance --dir data/finance/ --uploader-id <admin-uuid>

# 5. Run evaluation
python -m eval.run_eval
```

Results are saved to `backend/eval/results/eval_<timestamp>.csv` and PostgreSQL.

### Evaluation Metrics

| Metric | Description |
|---|---|
| Faithfulness | Are all claims in the answer supported by retrieved context? |
| Answer Relevancy | Does the answer address the question asked? |
| Context Recall | Did retrieval surface all relevant information needed? |
| Context Precision | Are retrieved chunks relevant, with minimal noise? |

### Results Storage

- CSV: `backend/eval/results/eval_YYYYMMDD_HHMMSS.csv`
- PostgreSQL: `eval_results` table (run_id, metric_name, score, run_at)
- Admin UI: Admin page → Eval tab displays latest run scores

### Limitations

- Requires live external services (PostgreSQL, Qdrant, OpenAI API); cannot run fully offline.
- RAGAS evaluation itself calls OpenAI (for LLM-as-a-judge metrics), incurring API cost.
- The 50-question dataset is synthetic-grounded in department data files; real-world production questions may vary.
- No automated CI test suite exists for the eval (test files were empty at baseline).
