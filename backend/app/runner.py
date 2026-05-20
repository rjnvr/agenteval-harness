import json
from sqlalchemy.orm import Session, joinedload

from backend.app import evaluator
from backend.app.agents import (
    AgentError,
    AgentOutput,
    judge_answer,
    run_anthropic_agent,
    run_google_agent,
    run_mock_agent,
    run_openai_agent,
    run_openrouter_agent,
    run_webhook_agent,
)
from backend.app.config import get_settings
from backend.app.dataset import acceptable_actions, all_fact_texts, expected_facts, required_facts, supporting_facts
from backend.app.models import EvalCase, EvalResult, EvalRun
from backend.app.pii import redact_value
from backend.app.schemas import RunRequest

PROVIDERS = {"mock", "anthropic", "openai", "google", "openrouter", "webhook"}


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
    if provider in {"gemini", "google_gemini"}:
        provider = "google"
    if provider in {"llama", "meta", "meta_llama"}:
        provider = "openrouter"
    if provider in {"byo", "custom", "http"}:
        provider = "webhook"
    return provider


def _provider_model(provider: str, requested_model: str | None) -> str:
    settings = get_settings()
    if requested_model:
        return requested_model
    if provider == "anthropic":
        return settings.claude_model
    if provider == "openai":
        return settings.openai_model
    if provider == "google":
        return settings.google_model
    if provider == "openrouter":
        return settings.openrouter_model
    if provider == "webhook":
        return "byo-agent-webhook"
    return "mock-deterministic"


def _provider_api_key(provider: str, per_run_key: str | None) -> str | None:
    if provider == "mock":
        return None
    return per_run_key.strip() if per_run_key and per_run_key.strip() else None


def create_eval_run(
    db: Session,
    request: RunRequest | str,
    case_ids: list[str] | None = None,
    *,
    status: str = "running",
) -> EvalRun:
    provider, selected_case_ids, requested_model, _per_run_key, judge_enabled, webhook_url, _webhook_headers = _run_options(request, case_ids)

    if provider not in PROVIDERS:
        raise ValueError("provider must be 'mock', 'anthropic', 'openai', 'google', 'openrouter', or 'webhook'")
    if provider == "webhook" and not (webhook_url and webhook_url.strip()):
        raise ValueError("webhook provider requires webhook_url")

    model = _provider_model(provider, requested_model)
    query = db.query(EvalCase).options(joinedload(EvalCase.document)).order_by(EvalCase.id)
    if selected_case_ids:
        query = query.filter(EvalCase.id.in_(selected_case_ids))
    cases = query.all()

    run = EvalRun(
        mode="claude" if provider == "anthropic" else provider,
        provider=provider,
        model=model,
        judge_enabled=judge_enabled,
        status=status,
        total_cases=len(cases),
    )
    db.add(run)
    db.flush()
    db.commit()
    db.refresh(run)
    return run


def _run_options(
    request: RunRequest | str,
    case_ids: list[str] | None = None,
) -> tuple[str, list[str] | None, str | None, str | None, bool, str | None, dict[str, str] | None]:
    if isinstance(request, str):
        return _effective_provider(request), case_ids, None, None, False, None, None
    return (
        _effective_provider(request),
        request.case_ids,
        request.model,
        request.api_key,
        request.judge_enabled,
        request.webhook_url,
        request.webhook_headers,
    )


def execute_eval_run(db: Session, run_id: int, request: RunRequest | str, case_ids: list[str] | None = None) -> EvalRun:
    provider, selected_case_ids, requested_model, per_run_key, judge_enabled, webhook_url, webhook_headers = _run_options(request, case_ids)
    model = _provider_model(provider, requested_model)
    api_key = _provider_api_key(provider, per_run_key)
    query = db.query(EvalCase).options(joinedload(EvalCase.document)).order_by(EvalCase.id)
    if selected_case_ids:
        query = query.filter(EvalCase.id.in_(selected_case_ids))
    cases = query.all()

    run = db.query(EvalRun).filter(EvalRun.id == run_id).first()
    if not run:
        raise ValueError("Run not found")

    run.status = "running"
    run.total_cases = len(cases)
    db.commit()

    for case in cases:
        facts = required_facts(case)
        support_facts = supporting_facts(case)
        retrieval_facts = all_fact_texts(case)
        actions = acceptable_actions(case)
        agent_failed = False
        try:
            if provider == "mock":
                output = run_mock_agent(case, case.document.text, facts)
            elif provider == "anthropic":
                output = run_anthropic_agent(case, case.document.text, model, api_key)
            elif provider == "openai":
                output = run_openai_agent(case, case.document.text, model, api_key)
            elif provider == "google":
                output = run_google_agent(case, case.document.text, model, api_key)
            elif provider == "openrouter":
                output = run_openrouter_agent(case, case.document.text, model, api_key)
            else:
                output = run_webhook_agent(case, case.document.text, webhook_url or "", webhook_headers)
        except (AgentError, json.JSONDecodeError, ValueError) as exc:
            output = _error_output(str(exc))
            agent_failed = True

        answer_match = evaluator.score_answer(output.answer, case.expected_answer, facts)
        matched_facts, missed_facts = evaluator.fact_coverage(output.answer, facts)
        fact_recall = round(len(matched_facts) / max(len(facts), 1), 3)
        fact_precision = evaluator.fact_precision(output.answer, case.document.text)
        hallucination = evaluator.hallucination_score(output.answer, case.document.text)
        tool_correct = output.action in actions
        action_input_score = evaluator.action_input_score(output.action_input, case.expected_answer, [*facts, *support_facts])
        retrieval_hit = evaluator.retrieval_hit(output.retrieved_chunks, retrieval_facts)
        groundedness = evaluator.groundedness(output.answer, output.retrieved_chunks)
        unsupported = evaluator.unsupported_claims(output.answer, case.document.text)
        judge_score = None
        if judge_enabled and not agent_failed and provider != "webhook":
            try:
                judge_score = judge_answer(provider, model, api_key, case.input, case.expected_answer, output.answer)
            except (AgentError, json.JSONDecodeError, ValueError):
                judge_score = None

        fail_mode = "agent_error" if agent_failed else evaluator.failure_type(
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
        fail_explanation = evaluator.failure_explanation(fail_mode)
        passed = (
            fail_mode == "none"
            and answer_match >= 0.72
            and fact_recall >= 1.0
            and tool_correct
            and action_input_score >= 0.12
            and retrieval_hit >= 0.5
            and hallucination < 0.45
            and groundedness >= 0.45
            and output.schema_valid
        )
        trace = redact_value(
            {
                "case_input": case.input,
                "document": {"id": case.document.id, "name": case.document.name, "category": case.document.category},
                "retrieved_chunks": output.retrieved_chunks,
                "agent_output": {
                    "answer": output.answer,
                    "action": output.action,
                    "action_input": output.action_input,
                    "schema_valid": output.schema_valid,
                },
                "scores": {
                    "answer_match": answer_match,
                    "fact_recall": fact_recall,
                    "fact_precision": fact_precision,
                    "tool_correct": tool_correct,
                    "action_input_score": action_input_score,
                    "retrieval_hit": retrieval_hit,
                    "groundedness": groundedness,
                    "hallucination_score": hallucination,
                    "judge_score": judge_score,
                },
                "matched_facts": matched_facts,
                "missed_facts": missed_facts,
                "supporting_facts": support_facts,
                "acceptable_actions": actions,
                "unsupported_claims": unsupported,
                "failure_mode": fail_mode,
                "failure_explanation": fail_explanation,
            }
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
                failure_type=fail_mode,
                failure_mode=fail_mode,
                failure_explanation=fail_explanation,
                passed=passed,
                retrieved_chunks_json=json.dumps(output.retrieved_chunks),
                unsupported_claims_json=json.dumps(unsupported),
                trace_json=json.dumps(trace),
            )
        )
        db.flush()
        results = list(run.results)
        run.total_cases = len(cases)
        run.pass_rate = round(sum(1 for result in results if result.passed) / max(len(results), 1), 3)
        run.avg_latency_ms = round(sum(result.latency_ms for result in results) / max(len(results), 1), 2)
        run.avg_cost_usd = round(sum(result.cost_usd for result in results) / max(len(results), 1), 6)
        db.commit()

    db.flush()
    results = list(run.results)
    run.total_cases = len(results)
    run.pass_rate = round(sum(1 for result in results if result.passed) / max(len(results), 1), 3)
    run.avg_latency_ms = round(sum(result.latency_ms for result in results) / max(len(results), 1), 2)
    run.avg_cost_usd = round(sum(result.cost_usd for result in results) / max(len(results), 1), 6)
    run.status = "completed"
    db.commit()
    db.refresh(run)
    return run


def fail_eval_run(db: Session, run_id: int) -> None:
    run = db.query(EvalRun).filter(EvalRun.id == run_id).first()
    if not run:
        return
    run.status = "failed"
    db.commit()


def run_evaluation(
    db: Session,
    request: RunRequest | str,
    case_ids: list[str] | None = None,
) -> EvalRun:
    run = create_eval_run(db, request, case_ids, status="running")
    return execute_eval_run(db, run.id, request, case_ids)
