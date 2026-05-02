# AgentEval Harness: Evaluation System for RAG + Tool-Using AI Agents

AgentEval Harness is a small full-stack evaluation system for document-based AI agents. It runs an agent against seeded business documents, checks the answer and selected action, and reports reliability metrics in a dashboard.

The default path uses deterministic mock mode, so the project runs locally without credentials. Claude mode is available for live model evaluation and reads credentials from the local environment through the Anthropic SDK.

## Screenshots

![AgentEval dashboard summary](docs/images/dashboard-summary.png)

![AgentEval failed case detail](docs/images/dashboard-case-detail.png)

## What It Measures

- Answer correctness against expected answers and facts
- Tool/action correctness
- Hallucination signals
- Latency
- Estimated cost per run
- Failure reason

## How Evaluation Works

Each test case is a small "golden" example in `data/seed_cases.json`. The document text is the source of truth, and the expected fields are written from that document:

- `expected_answer`: the concise answer the agent should give
- `expected_facts`: the specific document facts that must be present or clearly represented in the answer
- `expected_action`: the tool/action the agent should choose for the workflow

At runtime, the harness chunks the document, retrieves the most relevant chunks for the question using token overlap, and passes those chunks to the agent. The evaluator then compares the agent output against the golden case:

- `answer_match` checks overlap with the expected answer and required facts.
- `tool_correct` checks whether the selected action exactly matches `expected_action`.
- `hallucination_score` looks for unsupported money amounts or important terms in the answer that do not appear in the source document.
- `failure_type` summarizes the main issue, such as `missed_key_fact`, `wrong_action`, `hallucination`, or `agent_error`.

The retrieved context is shown in the run detail so a reviewer can see whether a failure came from retrieval, answer generation, or tool selection. For example, if the right chunk was retrieved but the answer missed a required fact, that points to an agent/prompt issue rather than a retrieval issue.

## Resume Bullets

- Built an agent evaluation harness to test document-based AI workflows across 20+ cases, measuring answer accuracy, tool-use correctness, latency, cost, and failure modes.
- Designed an agent eval system with test cases, scoring logic, failure-mode analysis, and dashboarding to improve reliability of RAG + tool-using AI workflows.

## Architecture

- `backend/app`: FastAPI API, SQLite persistence, RAG retrieval, agent runners, scoring logic
- `data/seed_cases.json`: 20 fake business documents and matching eval cases
- `frontend/src`: Vite React dashboard for running and inspecting evals
- `backend/tests`: dataset, evaluator, and API tests

The MVP uses SQLite by default. A different SQL database can be wired in by setting the database URL in the local environment.

## Backend Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn backend.app.main:app --reload
```

The API will run at `http://localhost:8000`.

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The dashboard will run at `http://localhost:5173`.

## Running Evals

Mock mode is the default and works without credentials:

```bash
curl -X POST http://localhost:8000/api/runs \
  -H "Content-Type: application/json" \
  -d '{"mode":"mock"}'
```

Claude mode can be selected from the dashboard or requested from the API with `{"mode":"claude"}` after local Anthropic SDK credentials are configured.

## API

- `GET /api/cases`: list seeded eval cases
- `POST /api/runs`: run all cases or selected case IDs with `mode=mock|claude`
- `GET /api/runs`: list recent eval runs
- `GET /api/runs/{run_id}`: inspect one run and its case results
- `GET /api/summary`: latest dashboard summary

## Testing

```bash
pytest
```

The test suite covers seed data loading, scoring behavior, mock-mode runs, and the core API endpoints.

