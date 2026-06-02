import json
from pathlib import Path
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session, joinedload

from backend.app.config import get_settings
from backend.app.database import SessionLocal, get_db, run_migrations
from backend.app.dataset import acceptable_actions, all_fact_texts, case_context, expected_decision, load_human_judge_labels, load_pii_samples, required_facts, seed_database, supporting_facts, upsert_cases
from backend.app.evaluator import average_score_breakdown, fact_coverage, failure_counts, score_breakdown
from backend.app.calibration import calibration_summary
from backend.app.agents import AgentError, summarize_eval_report
from backend.app.models import Document, EvalCase, EvalResult, EvalRun
from backend.app.pii import measure_recall
from backend.app.runner import _effective_provider, _provider_api_key, _provider_model, create_eval_run, execute_eval_run, fail_eval_run, run_evaluation
from backend.app.schemas import CaseUploadRequest, CaseUploadResponse, EvalCaseOut, EvalResultOut, EvalRunDetail, EvalRunOut, EvalSummaryRequest, RunRequest, SummaryOut

settings = get_settings()
app = FastAPI(title=settings.api_title)
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
FRONTEND_INDEX = FRONTEND_DIST / "index.html"

if (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    run_migrations()
    with SessionLocal() as db:
        seed_database(db)


def _case_out(case: EvalCase) -> EvalCaseOut:
    return EvalCaseOut(
        id=case.id,
        input=case.input,
        expected_answer=case.expected_answer,
        expected_facts=all_fact_texts(case),
        required_facts=required_facts(case),
        supporting_facts=supporting_facts(case),
        expected_action=case.expected_action,
        acceptable_actions=acceptable_actions(case),
        context=case_context(case),
        expected_decision=expected_decision(case),
        document=case.document,
    )

def _result_out(result: EvalResult) -> EvalResultOut:
    case = result.case
    facts = required_facts(case)
    matched_facts, missed_facts = fact_coverage(result.answer, facts)
    return EvalResultOut(
        id=result.id,
        case_id=result.case_id,
        document_name=case.document.name,
        question=case.input,
        expected_answer=case.expected_answer,
        expected_facts=all_fact_texts(case),
        required_facts=facts,
        supporting_facts=supporting_facts(case),
        matched_facts=matched_facts,
        missed_facts=missed_facts,
        expected_action=case.expected_action,
        acceptable_actions=acceptable_actions(case),
        answer=result.answer,
        action=result.action,
        action_input=result.action_input,
        answer_match=result.answer_match,
        fact_recall=result.fact_recall,
        fact_precision=result.fact_precision,
        tool_correct=result.tool_correct,
        action_input_score=result.action_input_score,
        retrieval_hit=result.retrieval_hit,
        groundedness=result.groundedness,
        schema_valid=result.schema_valid,
        judge_score=result.judge_score,
        hallucination_score=result.hallucination_score,
        slot_valid=result.slot_valid,
        preference_score=result.preference_score,
        timezone_correct=result.timezone_correct,
        proposed_slot=result.proposed_slot,
        unsupported_claims=list(json.loads(result.unsupported_claims_json or "[]")),
        latency_ms=result.latency_ms,
        cost_usd=result.cost_usd,
        failure_type=result.failure_type,
        failure_mode=result.failure_mode,
        failure_explanation=result.failure_explanation,
        passed=result.passed,
        retrieved_chunks=list(json.loads(result.retrieved_chunks_json)),
        trace=dict(json.loads(result.trace_json or "{}")),
        score_breakdown=score_breakdown(result),
    )


@app.get("/api/cases", response_model=list[EvalCaseOut])
def list_cases(db: Session = Depends(get_db)) -> list[EvalCaseOut]:
    cases = db.query(EvalCase).options(joinedload(EvalCase.document)).order_by(EvalCase.id).all()
    return [_case_out(case) for case in cases]


@app.post("/api/cases", response_model=CaseUploadResponse)
def upload_cases(request: CaseUploadRequest, db: Session = Depends(get_db)) -> CaseUploadResponse:
    if not request.cases:
        raise HTTPException(status_code=400, detail="At least one case is required")
    payload_cases = [case.model_dump() for case in request.cases]
    payload_docs = [doc.model_dump() for doc in request.documents]
    try:
        doc_count, case_count = upsert_cases(db, payload_docs, payload_cases, replace=request.replace)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CaseUploadResponse(
        documents_written=doc_count,
        cases_written=case_count,
        total_documents=db.query(Document).count(),
        total_cases=db.query(EvalCase).count(),
        replaced=request.replace,
    )


def _execute_run_in_background(run_id: int, request: RunRequest) -> None:
    with SessionLocal() as db:
        try:
            execute_eval_run(db, run_id, request)
        except Exception:
            fail_eval_run(db, run_id)
            raise


@app.post("/api/runs", response_model=EvalRunDetail)
def create_run(request: RunRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)) -> EvalRunDetail:
    try:
        if request.async_run:
            run = create_eval_run(db, request, status="queued")
            background_tasks.add_task(_execute_run_in_background, run.id, request)
        else:
            run = run_evaluation(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return get_run(run.id, db)


@app.get("/api/runs", response_model=list[EvalRunOut])
def list_runs(db: Session = Depends(get_db)) -> list[EvalRun]:
    return db.query(EvalRun).order_by(EvalRun.created_at.desc()).limit(25).all()


@app.get("/api/runs/{run_id}", response_model=EvalRunDetail)
def get_run(run_id: int, db: Session = Depends(get_db)) -> EvalRunDetail:
    run = (
        db.query(EvalRun)
        .options(joinedload(EvalRun.results).joinedload(EvalResult.case).joinedload(EvalCase.document))
        .filter(EvalRun.id == run_id)
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return EvalRunDetail(
        id=run.id,
        mode=run.mode,
        provider=run.provider,
        model=run.model,
        judge_enabled=run.judge_enabled,
        status=run.status,
        total_cases=run.total_cases,
        pass_rate=run.pass_rate,
        avg_latency_ms=run.avg_latency_ms,
        avg_cost_usd=run.avg_cost_usd,
        created_at=run.created_at,
        results=sorted((_result_out(result) for result in run.results), key=lambda result: result.case_id),
    )


@app.get("/api/runs/{run_id}/status", response_model=EvalRunDetail)
def get_run_status(run_id: int, db: Session = Depends(get_db)) -> EvalRunDetail:
    return get_run(run_id, db)


@app.get("/api/comparison")
def get_comparison(db: Session = Depends(get_db)) -> dict[str, object]:
    runs = (
        db.query(EvalRun)
        .options(joinedload(EvalRun.results))
        .order_by(EvalRun.created_at.desc())
        .limit(25)
        .all()
    )
    items: list[dict[str, object]] = []
    for run in runs:
        results = list(run.results)
        failed_results = [result for result in results if not result.passed]
        avg_answer_match = round(sum(result.answer_match for result in results) / max(len(results), 1), 3)
        avg_fact_recall = round(sum(result.fact_recall for result in results) / max(len(results), 1), 3)
        avg_groundedness = round(sum(result.groundedness for result in results) / max(len(results), 1), 3)
        breakdown = average_score_breakdown(results)
        items.append(
            {
                "id": run.id,
                "provider": run.provider,
                "model": run.model,
                "created_at": run.created_at.isoformat(),
                "total_cases": run.total_cases,
                "pass_rate": run.pass_rate,
                "avg_latency_ms": run.avg_latency_ms,
                "avg_cost_usd": run.avg_cost_usd,
                "avg_answer_match": avg_answer_match,
                "avg_fact_recall": avg_fact_recall,
                "avg_groundedness": avg_groundedness,
                "strict_pass_rate": run.pass_rate,
                "score_breakdown": breakdown,
                "avg_decision_correctness": breakdown["decision_correctness"],
                "avg_constraint_satisfaction": breakdown["constraint_satisfaction"],
                "avg_preference_adherence": breakdown["preference_adherence"],
                "avg_timezone_accuracy": breakdown["timezone_accuracy"],
                "avg_coordination_coverage": breakdown["coordination_coverage"],
                "avg_semantic_quality": breakdown["decision_correctness"],
                "avg_fact_completeness": breakdown["coordination_coverage"],
                "avg_tool_accuracy": breakdown["decision_correctness"],
                "avg_grounding": breakdown["constraint_satisfaction"],
                "avg_retrieval_quality": breakdown["coordination_coverage"],
                "failure_counts": failure_counts(results),
                "failed_cases": [
                    {
                        "case_id": result.case_id,
                        "failure_mode": result.failure_mode,
                        "answer_match": result.answer_match,
                    }
                    for result in sorted(failed_results, key=lambda item: item.case_id)[:8]
                ],
            }
        )
    return {"runs": items}


def _latest_run_report(run: EvalRun) -> dict[str, object]:
    results = sorted(run.results, key=lambda result: result.case_id)
    failures = [result for result in results if not result.passed]
    return {
        "run_id": run.id,
        "provider": run.provider,
        "model": run.model,
        "judge_enabled": run.judge_enabled,
        "total_cases": run.total_cases,
        "pass_rate": run.pass_rate,
        "strict_pass_rate": run.pass_rate,
        "score_breakdown": average_score_breakdown(results),
        "avg_latency_ms": run.avg_latency_ms,
        "avg_cost_usd": run.avg_cost_usd,
        "failure_counts": failure_counts(results),
        "cases": [
            {
                "case_id": result.case_id,
                "document_name": result.case.document.name,
                "question": result.case.input,
                "passed": result.passed,
                "failure_mode": result.failure_mode,
                "failure_explanation": result.failure_explanation,
                "answer_match": result.answer_match,
                "fact_recall": result.fact_recall,
                "tool_correct": result.tool_correct,
                "slot_valid": result.slot_valid,
                "preference_score": result.preference_score,
                "timezone_correct": result.timezone_correct,
                "proposed_slot": result.proposed_slot,
                "missed_facts": fact_coverage(result.answer, required_facts(result.case))[1],
                "unsupported_claims": list(json.loads(result.unsupported_claims_json or "[]")),
            }
            for result in results
        ],
        "failed_case_sample": [
            {
                "case_id": result.case_id,
                "failure_mode": result.failure_mode,
                "answer_match": result.answer_match,
                "fact_recall": result.fact_recall,
            }
            for result in failures[:8]
        ],
    }


@app.post("/api/runs/latest/summary")
def summarize_latest_run(request: EvalSummaryRequest, db: Session = Depends(get_db)) -> dict[str, object]:
    latest = (
        db.query(EvalRun)
        .options(joinedload(EvalRun.results).joinedload(EvalResult.case).joinedload(EvalCase.document))
        .order_by(EvalRun.created_at.desc())
        .first()
    )
    if not latest:
        raise HTTPException(status_code=400, detail="Run at least one eval before generating a summary.")

    provider = _effective_provider(request)
    model = _provider_model(provider, request.model)
    api_key = _provider_api_key(provider, request.api_key)
    report = _latest_run_report(latest)
    try:
        summary = summarize_eval_report(provider, model, api_key, report)
    except (AgentError, json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"run_id": latest.id, "provider": provider, "model": model, "summary": summary, "report": report}


@app.get("/api/summary", response_model=SummaryOut)
def get_summary(db: Session = Depends(get_db)) -> SummaryOut:
    latest = db.query(EvalRun).order_by(EvalRun.created_at.desc()).first()
    runs = db.query(EvalRun).all()
    latest_results: list[EvalResult] = []
    if latest:
        latest_results = (
            db.query(EvalResult)
            .options(joinedload(EvalResult.case).joinedload(EvalCase.document))
            .filter(EvalResult.run_id == latest.id)
            .all()
        )
    total_tests = sum(run.total_cases for run in runs)
    return SummaryOut(
        total_runs=len(runs),
        total_tests_run=total_tests,
        latest_run=latest,
        pass_rate=latest.pass_rate if latest else 0,
        avg_latency_ms=latest.avg_latency_ms if latest else 0,
        avg_cost_usd=latest.avg_cost_usd if latest else 0,
        failure_counts=failure_counts(latest_results),
        failed_cases=[_result_out(result) for result in latest_results if not result.passed],
        score_breakdown=average_score_breakdown(latest_results),
        calibration=calibration_summary(load_human_judge_labels()),
        pii_redaction=measure_recall(load_pii_samples()),
    )


@app.get("/api/calibration")
def get_calibration() -> dict[str, object]:
    return calibration_summary(load_human_judge_labels())


@app.get("/api/pii-redaction")
def get_pii_redaction() -> dict[str, object]:
    return measure_recall(load_pii_samples())


@app.get("/")
def serve_frontend() -> FileResponse:
    if not FRONTEND_INDEX.exists():
        raise HTTPException(status_code=404, detail="Frontend build not found")
    return FileResponse(FRONTEND_INDEX)


@app.get("/{path:path}")
def serve_frontend_route(path: str) -> FileResponse:
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not Found")
    if not FRONTEND_INDEX.exists():
        raise HTTPException(status_code=404, detail="Frontend build not found")
    return FileResponse(FRONTEND_INDEX)
