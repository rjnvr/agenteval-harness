import json
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, joinedload

from backend.app.config import get_settings
from backend.app.database import Base, SessionLocal, engine, ensure_schema, get_db
from backend.app.dataset import expected_facts, seed_database
from backend.app.evaluator import fact_coverage, failure_counts
from backend.app.models import EvalCase, EvalResult, EvalRun
from backend.app.runner import run_evaluation
from backend.app.schemas import EvalCaseOut, EvalResultOut, EvalRunDetail, EvalRunOut, RunRequest, SummaryOut

settings = get_settings()
app = FastAPI(title=settings.api_title)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_schema()
    with SessionLocal() as db:
        seed_database(db)


def _case_out(case: EvalCase) -> EvalCaseOut:
    return EvalCaseOut(
        id=case.id,
        input=case.input,
        expected_answer=case.expected_answer,
        expected_facts=expected_facts(case),
        expected_action=case.expected_action,
        document=case.document,
    )

def _result_out(result: EvalResult) -> EvalResultOut:
    case = result.case
    facts = expected_facts(case)
    matched_facts, missed_facts = fact_coverage(result.answer, facts)
    return EvalResultOut(
        id=result.id,
        case_id=result.case_id,
        document_name=case.document.name,
        question=case.input,
        expected_answer=case.expected_answer,
        expected_facts=facts,
        matched_facts=matched_facts,
        missed_facts=missed_facts,
        expected_action=case.expected_action,
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
        unsupported_claims=list(json.loads(result.unsupported_claims_json or "[]")),
        latency_ms=result.latency_ms,
        cost_usd=result.cost_usd,
        failure_type=result.failure_type,
        passed=result.passed,
        retrieved_chunks=list(json.loads(result.retrieved_chunks_json)),
    )


@app.get("/api/cases", response_model=list[EvalCaseOut])
def list_cases(db: Session = Depends(get_db)) -> list[EvalCaseOut]:
    cases = db.query(EvalCase).options(joinedload(EvalCase.document)).order_by(EvalCase.id).all()
    return [_case_out(case) for case in cases]


@app.post("/api/runs", response_model=EvalRunDetail)
def create_run(request: RunRequest, db: Session = Depends(get_db)) -> EvalRunDetail:
    try:
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
    )
