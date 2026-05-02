import json
from sqlalchemy.orm import Session, joinedload

from backend.app import evaluator
from backend.app.agents import AgentError, AgentOutput, run_claude_agent, run_mock_agent
from backend.app.config import get_settings
from backend.app.dataset import expected_facts
from backend.app.models import EvalCase, EvalResult, EvalRun


def _error_output(message: str) -> AgentOutput:
    return AgentOutput(
        answer=f"Agent error: {message}",
        action="",
        action_input="",
        retrieved_chunks=[],
        latency_ms=1,
        cost_usd=0.0,
    )


def run_evaluation(db: Session, mode: str, case_ids: list[str] | None = None) -> EvalRun:
    if mode not in {"mock", "claude"}:
        raise ValueError("mode must be 'mock' or 'claude'")

    query = db.query(EvalCase).options(joinedload(EvalCase.document)).order_by(EvalCase.id)
    if case_ids:
        query = query.filter(EvalCase.id.in_(case_ids))
    cases = query.all()
    settings = get_settings()

    run = EvalRun(mode=mode, status="completed", total_cases=len(cases))
    db.add(run)
    db.flush()

    for case in cases:
        facts = expected_facts(case)
        try:
            if mode == "mock":
                output = run_mock_agent(case, case.document.text, facts)
                agent_failed = False
            else:
                output = run_claude_agent(
                    case,
                    case.document.text,
                    settings.claude_model,
                    settings.anthropic_api_key,
                )
                agent_failed = False
        except (AgentError, json.JSONDecodeError, ValueError) as exc:
            output = _error_output(str(exc))
            agent_failed = True

        answer_match = evaluator.score_answer(output.answer, case.expected_answer, facts)
        hallucination = evaluator.hallucination_score(output.answer, case.document.text)
        tool_correct = output.action == case.expected_action
        fail_type = "agent_error" if agent_failed else evaluator.failure_type(
            answer_match, tool_correct, hallucination, output.answer, facts
        )
        passed = fail_type == "none" and answer_match >= 0.72 and tool_correct and hallucination < 0.45

        db.add(
            EvalResult(
                run_id=run.id,
                case_id=case.id,
                answer=output.answer,
                action=output.action,
                action_input=output.action_input,
                answer_match=answer_match,
                tool_correct=tool_correct,
                hallucination_score=hallucination,
                latency_ms=output.latency_ms,
                cost_usd=output.cost_usd,
                failure_type=fail_type,
                passed=passed,
                retrieved_chunks_json=json.dumps(output.retrieved_chunks),
            )
        )

    db.flush()
    results = list(run.results)
    run.total_cases = len(results)
    run.pass_rate = round(sum(1 for result in results if result.passed) / max(len(results), 1), 3)
    run.avg_latency_ms = round(sum(result.latency_ms for result in results) / max(len(results), 1), 2)
    run.avg_cost_usd = round(sum(result.cost_usd for result in results) / max(len(results), 1), 6)
    db.commit()
    db.refresh(run)
    return run
