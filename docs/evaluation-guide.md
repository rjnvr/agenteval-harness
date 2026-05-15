# AgentEval Evaluation Guide

This guide explains AgentEval from the ground up. It is written for readers who understand basic software concepts but are new to RAG systems, tool-using agents, and evaluation metrics.

## What AgentEval Is Evaluating

AgentEval tests a document-based AI agent. The agent receives a business document, a question, and a short list of allowed workflow actions. It must do two things:

1. Answer the question using only the document.
2. Pick the right action for the workflow.

For example, a document might describe an invoice, insurance claim, contract, construction change order, or compliance note. The agent might need to approve an invoice, request more information, flag a cost risk, or escalate a compliance review.

The point of the harness is not just to ask "did the answer sound good?" It checks whether the answer was grounded in the source document, whether the right facts were included, whether the right tool/action was selected, and whether the result can be inspected later.

## Golden Test Cases

Each test case in `data/seed_cases.json` is a golden example. A golden example is a case where the expected behavior is already known.

Each case has:

- `input`: the question given to the agent.
- `expected_answer`: the concise answer the agent should produce.
- `expected_facts`: the facts from the document that must appear in the answer.
- `expected_action`: the workflow action the agent should choose.

The document text is the source of truth. If a fact is not in the document, the agent should not invent it.

## How A Run Works

An evaluation run follows the same basic path for every case:

1. The backend loads a document and its golden test case.
2. The retrieval layer splits the document into chunks.
3. The retrieval layer selects the chunks that overlap most with the user question.
4. The agent receives the question, retrieved chunks, and allowed actions.
5. The agent returns JSON with an `answer`, `action`, and `action_input`.
6. The evaluator compares the agent output with the golden case.
7. The dashboard shows scores, failures, retrieved context, and the agent output.

Mock mode uses deterministic local behavior, so the project runs without API keys. Live mode can call Anthropic Claude or OpenAI models if credentials are provided.

## Reading The Dashboard

The dashboard starts with run-level metrics:

- Tests run: how many case results have been recorded.
- Pass rate: the share of cases that met all pass criteria.
- Average latency: the average time per case.
- Average cost: the estimated model cost per case.

The failed cases table is the best place to debug behavior. Expand a failed row to inspect:

- the original question
- the expected answer and expected action
- the actual agent answer and action
- matched facts and missed facts
- unsupported claims
- retrieved document chunks
- metric scores for that case

This helps separate different problems. If the retrieved context did not include the key facts, the retrieval step likely failed. If the right context was retrieved but the answer missed facts, the agent output likely failed. If the answer is good but the action is wrong, the tool-selection behavior needs work.

## Metric Reference

### `answer_match`

Measures how closely the agent answer matches the expected answer and required facts.

Higher is better. A high score means the answer used many of the same important terms and covered the expected facts. A low score means the answer missed important content or answered a different question.

### `fact_recall`

Measures how many required facts appeared in the answer.

If a case has three expected facts and the answer includes all three, fact recall is `1.0`. If it includes only one, fact recall is about `0.33`.

This is useful because an answer can sound reasonable while still omitting a required amount, deadline, missing document, or policy condition.

### `fact_precision`

Estimates how much of the answer is supported by the source document.

Higher is better. A low score means the answer contains unsupported terms or money amounts. In this project, fact precision is closely related to the hallucination check.

### `tool_correct`

Checks whether the selected action exactly matches `expected_action`.

This is a strict true/false metric. If the expected action is `request_more_info` and the agent selects `flag_risk`, the tool is wrong even if the written answer is mostly correct.

### `action_input_score`

Checks whether the argument passed to the selected action includes the right reason, amount, item, or task.

For example, selecting `request_more_info` is not enough. The agent should also say what information is missing, such as photos, an invoice, or a security report.

### `retrieval_hit`

Measures whether the retrieved chunks contain the expected facts.

This helps diagnose retrieval problems. If `retrieval_hit` is low, the agent may not have received the right source text. If `retrieval_hit` is high but the answer is bad, the issue is more likely in the agent's reasoning or response formatting.

### `groundedness`

Measures whether the answer is supported by the retrieved chunks.

This differs from fact precision because it uses only the retrieved context, not the full document. A low groundedness score means the answer included details that were not present in the context actually given to the agent.

### `schema_valid`

Checks whether live model output followed the required JSON shape.

The harness expects:

```json
{
  "answer": "string",
  "action": "supported_action",
  "action_input": "string"
}
```

If the model returns prose, invalid JSON, missing fields, or an unsupported action, `schema_valid` is false and the case is treated as an agent error.

### `judge_score`

An optional LLM-as-judge score for semantic correctness.

When enabled for live providers, the selected model grades the agent answer against the expected answer and returns a score between `0` and `1`. This can catch meaning that simple token overlap misses, but it is slower, costs more, and depends on the judge model. Deterministic scoring remains the default.

### `hallucination_score`

Looks for unsupported money amounts or important terms in the answer that do not appear in the source document.

Higher is worse. A score near `1.0` means the answer likely invented information, such as a dollar amount that was not in the document.

### Latency

The time it took to run the agent for a case, measured in milliseconds.

Latency is useful for comparing providers and prompts, but a fast wrong answer is still a failure. Treat latency as an operational metric, not a quality metric.

### Cost

The estimated model cost for a case.

Mock runs cost `$0.0000`. Live runs estimate cost from token usage and provider pricing assumptions in the backend.

### Pass Or Fail

A case passes only when the main quality gates pass together:

- answer quality is high enough
- all expected facts are recalled
- the selected tool/action is correct
- action input has enough relevant detail
- retrieval found enough expected facts
- hallucination risk is low
- groundedness is high enough
- output schema is valid

This makes the harness strict by design. The goal is to find reliability problems, not to give partial credit to answers that would still be risky in a workflow.

### `failure_type`

Summarizes the main reason a case failed.

Current values include:

- `missed_key_fact`: the answer left out required document facts.
- `wrong_action`: the selected workflow action was wrong or the action input was too weak.
- `hallucination`: the answer added unsupported information.
- `agent_error`: the model call failed or the output schema was invalid.
- `low_answer_match`: the answer did not match the expected answer closely enough.
- `none`: no failure was detected.

The failure type is a shortcut for triage. The expanded case details show the evidence behind the label.

## Common Failure Examples

### The Right Answer With The Wrong Action

The agent correctly explains that an invoice is missing a purchase order, but selects `approve_invoice` instead of `request_more_info`.

This is a tool-use failure. The language answer may be useful, but the workflow action would do the wrong thing.

### The Right Context With Missing Facts

The retrieved context includes the missing invoice, late submission, and missing photos, but the answer mentions only the late submission.

This is an answer-generation failure. Retrieval worked, but the agent did not use all required facts.

### A Plausible But Unsupported Amount

The document says the cost increase is `$18,500`, but the answer says `$19,000`.

This is a hallucination or grounding failure. Even a small unsupported amount matters in business workflows.

### Invalid JSON From A Live Model

The model returns a paragraph instead of the required JSON object.

This is a schema failure. The app cannot reliably parse the answer, action, and action input.

## How To Use The Metrics Together

No single metric tells the full story. Read them as a chain:

1. Did retrieval find the right evidence? Check `retrieval_hit`.
2. Did the answer use that evidence? Check `fact_recall`, `answer_match`, and `groundedness`.
3. Did the answer avoid invented information? Check `fact_precision` and `hallucination_score`.
4. Did the agent choose the right workflow action? Check `tool_correct` and `action_input_score`.
5. Did the model return machine-readable output? Check `schema_valid`.
6. How expensive or slow was the run? Check cost and latency.

That chain is what makes AgentEval useful: it turns an agent's behavior into specific, inspectable failure modes.
