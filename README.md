# AgentEval Harness: Evaluation System for Coordination & Scheduling Agents

AgentEval Harness is a full-stack evaluation system for AI scheduling and coordination agents. It runs golden coordination scenarios, checks whether the agent chose the right scheduling action, validates proposed slots against calendars and preferences, and reports failures in a dashboard.

The default `mock` provider is a competent deterministic coordinator and runs locally without credentials. The `naive` provider intentionally ignores preferences, timezones, and missing availability in selected cases so the dashboard can demonstrate real scheduling failure modes. Live runs support Anthropic, OpenAI, Google Gemini, OpenRouter, and a Bring-Your-Own-Agent webhook.

New to evals? Read the [beginner evaluation guide](docs/evaluation-guide.md).

## What It Measures

The harness is aligned to coordination agents like Vela: assistants that are CC'd on email, SMS, WhatsApp, or Slack and must coordinate meetings from natural language while respecting context-specific preferences.

| Axis | Metric fields | What it catches |
| --- | --- | --- |
| **Decision Correctness** | `tool_correct` | Wrong action: book vs propose times vs decline vs request availability vs reschedule. |
| **Constraint Satisfaction** | `slot_valid`, `groundedness` | Double-booking, outside working hours, unknown availability, unsupported calendar claims. |
| **Preference Adherence** | `preference_score` | Context-sensitive rules such as "John will take a 7 AM call with a CEO but not a peer." |
| **Timezone Accuracy** | `timezone_correct` | Wrong timezone conversions or proposing 9 AM London when the request meant 9 AM Pacific. |
| **Coordination Coverage** | `fact_recall`, `retrieval_hit` | Missing participants, calendars, preference rules, or required follow-ups. |

Failure modes are scheduling-specific: `wrong_action`, `double_booking`, `outside_working_hours`, `preference_violation`, `timezone_error`, `missed_participant`, `premature_booking`, `no_followup`, `unsupported_availability`, `schema_invalid`, `agent_error`, and `low_answer_quality`.

## How Evaluation Works

Each case in `data/seed_cases.json` includes:

- A natural-language scheduling request.
- Structured context: participants, roles, timezones, working hours, busy blocks, availability status, constraints, and preference rules.
- An expected decision: action plus a proposed slot, info needed, or decline reason.
- Expected considerations the answer should mention.

At runtime, the harness assembles context lines from the scenario summary and structured calendars/preferences, sends them to the selected agent, and expects JSON:

```json
{
  "answer": "Propose 10:00-10:30 AM Pacific because John does not take 7 AM peer calls.",
  "action": "propose_times",
  "action_input": "10 AM Pacific; respects John's early-call preference",
  "proposed_slot": {"start": "2026-06-10T10:00:00-07:00", "end": "2026-06-10T10:30:00-07:00"},
  "reasoning": "All attendees are free and the CEO-only early exception does not apply."
}
```

The evaluator combines deterministic slot/preference/timezone checks with text coverage and grounding heuristics. Strict pass requires the right decision, a valid slot when one is proposed, full preference adherence, correct timezone handling, enough coordination coverage, and valid schema.

## Why This Maps to Vela

Vela's hard problem is thousands of context-dependent coordination decisions per day. This harness makes those decisions testable: it can catch early-call preference violations, missing follow-ups, timezone mistakes, double-booking, and unsupported availability before an agent reaches paying customers. The webhook mode means an external scheduling agent can be scored without changing this repo.

## Architecture

- `backend/app`: FastAPI API, SQLite/Postgres persistence, agent runners, context assembly, scoring logic.
- `data/seed_cases.json`: 20 scheduling/coordination golden cases.
- `frontend/src`: Vite React dashboard for running and inspecting evals.
- `backend/tests`: dataset, evaluator, agent, and API tests.

SQLite is used by default locally. For production, set `AGENTEVAL_DATABASE_URL` to hosted Postgres such as Supabase or Neon.

## Backend Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn backend.app.main:app --reload
```

The API runs at `http://localhost:8000`. Database migrations run automatically on startup.

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The dashboard runs at `http://localhost:5173`.

## Running Evals

```bash
curl -X POST http://localhost:8000/api/runs \
  -H "Content-Type: application/json" \
  -d '{"provider":"mock"}'
```

Use `naive` to demonstrate the harness catching failures:

```bash
curl -X POST http://localhost:8000/api/runs \
  -H "Content-Type: application/json" \
  -d '{"provider":"naive"}'
```

Live providers can be selected in the dashboard or requested with `provider` set to `anthropic`, `openai`, `google`, or `openrouter`. Per-run API keys are accepted and are not stored.

## Bring Your Own Agent

Set `provider` to `webhook` and pass `webhook_url`. The harness posts each scheduling case and scores your response with the same pipeline.

```bash
curl -X POST http://localhost:8000/api/runs \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "webhook",
    "webhook_url": "https://your-scheduler.example.com/run",
    "webhook_headers": {"Authorization": "Bearer YOUR_TOKEN"},
    "case_ids": ["case_001", "case_003"]
  }'
```

Webhook responses must include `answer`, `action`, and `action_input`. Include `proposed_slot` for `propose_times`, `book_meeting`, and `propose_alternative`.

## API

- `GET /api/cases`: list seeded scheduling cases.
- `POST /api/runs`: run cases with `provider=mock|naive|anthropic|openai|google|openrouter|webhook`.
- `GET /api/runs`: list recent eval runs.
- `GET /api/runs/{run_id}`: inspect results and assembled context.
- `GET /api/runs/{run_id}/status`: poll async run status.
- `GET /api/summary`: latest dashboard summary.

## Testing

```bash
pytest
cd frontend && npm run build
```

## Resume Bullets

- Repurposed AgentEval into a coordination-agent eval harness with 20 scheduling golden cases, scoring **Decision Correctness**, **Constraint Satisfaction**, **Preference Adherence**, **Timezone Accuracy**, and **Coordination Coverage**.
- Built deterministic validators for double-booking, working-hours violations, context-sensitive preferences, missing availability follow-ups, and timezone conversion errors.
- Shipped `mock`, `naive`, live-provider, and BYO-webhook modes so external scheduling agents can be evaluated against the same failure taxonomy.
