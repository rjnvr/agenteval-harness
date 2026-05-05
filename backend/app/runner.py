import json
from sqlalchemy.orm import Session, joinedload

from backend.app import evaluator
from backend.app.agents import (
    AgentError,
    AgentOutput,
    judge_answer,
    run_anthropic_agent,
    run_mock_agent,
    run_openai_agent,
)
from backend.app.config import get_settings
from backend.app.dataset import expected_facts
from backend.app.models import EvalCase, EvalResult, EvalRun
from backend.app.schemas import RunRequest

PROVIDERS = {"mock", "anthropic", "openai"}


def _error_output(message: str) -> AgentOutput:
    return AgentOutput(
        answer=f"Agent error: {message}",
        action="",
        action_input="",
        retrieved_chunks=[],
        latency_ms=1,
        cost_usd=0.0,
        schema_valid=False,
    )


def _effective_provider(request: RunRequest | str) -> str:
    if isinstance(request, str):
        provider = request
    else:
        provider = request.mode or request.provider
    provider = provider.strip().lower()
    if provider == "claude":
        provider = "anthropic"
    return provider


def _provider_model(provider: str, requested_model: str | None) -> str:
    settings = get_settings()
    if requested_model:
        return requested_model
    if provider == "anthropic":
        return settings.claude_model
    if provider == "openai":
        return settings.openai_model
    return "mock-deterministic"


def _provider_api_key(provider: str, per_run_key: str | None) -> str | None:
    if per_run_key:
        return per_run_key
    settings = get_settings()
    if provider == "anthropic":
        return settings.anthropic_api_key
    if provider == "openai":
        return settings.openai_api_key
    return None


def run_evaluation(
    db: Session,
    request: RunRequest | str,
    case_ids: list[str] | None = None,
) -> EvalRun:
    if isinstance(request, str):
        provider = _effective_provider(request)
        selected_case_ids = case_ids
        requested_model = None
        per_run_key = None
        judge_enabled = False
    else:
        provider = _effective_provider(request)
        selected_case_ids = request.case_ids
        requested_model = request.model
        per_run_key = request.api_key
        judge_enabled = request.judge_enabled

    if provider not in PROVIDERS:
        raise ValueError("provider must be 'mock', 'anthropic', or 'openai'")

    model = _provider_model(provider, requested_model)
    api_key = _provider_api_key(provider, per_run_key)
    query = db.query(EvalCase).options(joinedload(EvalCase.document)).order_by(EvalCase.id)
    if selected_case_ids:
        query = query.filter(EvalCase.id.in_(selected_case_ids))
    cases = query.all()

    run = EvalRun(
        mode="claude" if provider == "anthropic" else provider,
        provider=provider,
        model=model,
        judge_enabled=judge_enabled,
        status="completed",
        total_cases=len(cases),
    )
    db.add(run)
    db.flush()

    for case in cases:
        facts = expected_facts(case)
        agent_failed = False
        try:
            if provider == "mock":
                output = run_mock_agent(case, case.document.text, facts)
            elif provider == "anthropic":
                output = run_anthropic_agent(case, case.document.text, model, api_key)
            else:
                output = run_openai_agent(case, case.document.text, model, api_key)
        except (AgentError, json.JSONDecodeError, ValueError) as exc:
            output = _error_output(str(exc))
            agent_failed = True

        answer_match = evaluator.score_answer(output.answer, case.expected_answer, facts)
        matched_facts, missed_facts = evaluator.fact_coverage(output.answer, facts)
        fact_recall = round(len(matched_facts) / max(len(facts), 1), 3)
        fact_precision = evaluator.fact_precision(output.answer, case.document.text)
        hallucination = evaluator.hallucination_score(output.answer, case.document.text)
        tool_correct = output.action == case.expected_action
        action_input_score = evaluator.action_input_score(output.action_input, case.expected_answer, facts)
        retrieval_hit = evaluator.retrieval_hit(output.retrieved_chunks, facts)
        groundedness = evaluator.groundedness(output.answer, output.retrieved_chunks)
        unsupported = evaluator.unsupported_claims(output.answer, case.document.text)
        judge_score = None
        if judge_enabled and not agent_failed:
            try:
                judge_score = judge_answer(provider, model, api_key, case.input, case.expected_answer, output.answer)
            except (AgentError, json.JSONDecodeError, ValueError):
                judge_score = None

        fail_type = "agent_error" if agent_failed else evaluator.failure_type(
            answer_match,
            tool_correct,
            hallucination,
            output.answer,
            facts,
            schema_valid=output.schema_valid,
            action_input_score_value=action_input_score,
            retrieval_hit_value=retrieval_hit,
            groundedness_value=groundedness,
        )
        passed = (
            fail_type == "none"
            and answer_match >= 0.72
            and fact_recall >= 1.0
            and tool_correct
            and action_input_score >= 0.12
            and retrieval_hit >= 0.5
            and hallucination < 0.45
            and groundedness >= 0.45
            and output.schema_valid
        )

        db.add(
            EvalResult(
                run_id=run.id,
                case_id=case.id,
                answer=output.answer,
                action=output.action,
                action_input=output.action_input,
                answer_match=answer_match,
                fact_recall=fact_recall,
                fact_precision=fact_precision,
                tool_correct=tool_correct,
                action_input_score=action_input_score,
                retrieval_hit=retrieval_hit,
                groundedness=groundedness,
                schema_valid=output.schema_valid,
                judge_score=judge_score,
                hallucination_score=hallucination,
                latency_ms=output.latency_ms,
                cost_usd=output.cost_usd,
                failure_type=fail_type,
                passed=passed,
                retrieved_chunks_json=json.dumps(output.retrieved_chunks),
                unsupported_claims_json=json.dumps(unsupported),
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
