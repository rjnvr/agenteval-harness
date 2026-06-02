# AgentEval Evaluation Guide

This guide explains the scheduling version of AgentEval. It is written for readers who are new to agent evaluation but understand basic software concepts.

## What AgentEval Is Evaluating

AgentEval tests an AI coordination agent. The agent receives a scheduling request, assembled context, and a list of allowed actions. It must:

1. Understand the request.
2. Use participant calendars, timezones, working hours, and preferences.
3. Choose the correct scheduling action.
4. Return a supported slot when a slot is appropriate.

Example actions are `propose_times`, `book_meeting`, `decline`, `propose_alternative`, `request_availability`, and `escalate_to_human`.

The point is not just whether the answer sounds reasonable. The harness checks whether the agent made the right coordination decision and whether that decision is safe to execute.

## Golden Test Cases

Each case in `data/seed_cases.json` is a known-good scheduling scenario. A case includes:

- `input`: the natural-language request.
- `expected_answer`: the concise answer the agent should give.
- `expected_facts`: coordination considerations the answer should cover.
- `expected_action`: the correct scheduling decision.
- `context`: structured participants, calendars, working hours, timezones, availability status, and preference rules.
- `expected_decision`: the expected slot, follow-up, or decline reason.

The 20 seeded cases include preference traps, timezone spread, double-booking traps, missing availability, reschedules, and hard declines.

## How A Run Works

1. The backend loads a golden case.
2. The context layer assembles scenario, participant, calendar, timezone, and preference lines.
3. The selected provider receives the request, allowed actions, and assembled context.
4. The provider returns JSON with `answer`, `action`, `action_input`, and optional `proposed_slot`.
5. The evaluator checks the output against the expected decision.
6. The dashboard shows pass/fail, failure mode, metrics, proposed slot, and assembled context.

`mock` is a competent deterministic coordinator. `naive` intentionally ignores important context so the dashboard can show failures without API keys.

## Required JSON Shape

```json
{
  "answer": "string",
  "action": "supported_action",
  "action_input": "string",
  "proposed_slot": {"start": "2026-06-10T10:00:00-07:00", "end": "2026-06-10T10:30:00-07:00"},
  "reasoning": "string"
}
```

`proposed_slot` should be present for `propose_times`, `book_meeting`, and `propose_alternative`. It should use ISO datetimes with timezone offsets.

## Metric Reference

### Decision Correctness

Backed by `tool_correct`.

Checks whether the agent chose the right scheduling action. Booking when it should request availability is a decision failure, even if the message is polite.

### Constraint Satisfaction

Backed by `slot_valid` and `groundedness`.

Checks whether a proposed slot is free for every participant, within working hours, and supported by the assembled context. This catches double-booking, outside-hours scheduling, and invented availability.

### Preference Adherence

Backed by `preference_score`.

Checks context-sensitive rules. The signature example is: John will take a 7 AM call with a CEO, but not with a peer. A valid calendar slot can still fail if it violates this preference.

### Timezone Accuracy

Backed by `timezone_correct`.

Checks whether the proposed slot represents the expected instant. This catches mistakes like interpreting "Thursday morning Pacific" as 9 AM London.

### Coordination Coverage

Backed by `fact_recall` and `retrieval_hit`.

Checks whether the agent considered the required participants, preferences, calendars, and follow-ups. A low score often means the agent missed a relevant person or constraint.

### Schema Validity

Backed by `schema_valid`.

Checks whether live model or webhook output followed the JSON contract. Invalid JSON, missing fields, or unsupported actions fail this gate.

### Latency And Cost

Latency is measured per case in milliseconds. Cost is estimated from provider token usage where available. These are operational metrics; they do not compensate for unsafe scheduling decisions.

## Failure Modes

The failure taxonomy is scheduling-specific:

- `wrong_action`: the agent chose the wrong scheduling decision.
- `double_booking`: the proposed slot overlaps a busy block or fails working-hour constraints.
- `outside_working_hours`: the proposed slot is outside a participant's allowed hours.
- `preference_violation`: the agent ignored a contextual rule.
- `timezone_error`: the proposed instant or conversion is wrong.
- `missed_participant`: the agent missed a participant or required consideration.
- `premature_booking`: the agent booked before enough availability was known.
- `no_followup`: the agent should have requested availability but did not.
- `unsupported_availability`: the agent claimed a slot was supported when context did not support it.
- `schema_invalid`: the response was not parseable or used an unsupported action.
- `agent_error`: provider or webhook execution failed.
- `low_answer_quality`: the answer did not match the expected decision well enough.

## Reading A Failed Case

Expand a failed row in the dashboard and inspect:

- Expected action and expected answer.
- Agent answer, action, action input, and proposed slot.
- Slot validity, preference score, timezone correctness, context hit, and coverage.
- Matched and missed considerations.
- Assembled context lines.
- Failure rationale.

This separates common root causes. If context hit is high but preference adherence is low, the agent saw the rule and ignored it. If timezone accuracy is low, the issue is conversion or representation. If slot validity is false, inspect busy blocks and working hours.

## How To Use The Metrics Together

Read the metrics as a chain:

1. Did the agent receive the right context? Check context hit.
2. Did it choose the right decision? Check decision correctness.
3. If it proposed a time, is the slot legal? Check constraint satisfaction.
4. Did it honor preferences? Check preference adherence.
5. Did it convert timezones correctly? Check timezone accuracy.
6. Did it explain the relevant considerations? Check coordination coverage.

That chain is what makes the harness useful: it turns vague scheduling behavior into specific, inspectable failures.
