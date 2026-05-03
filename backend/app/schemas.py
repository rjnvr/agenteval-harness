from datetime import datetime
from pydantic import BaseModel, ConfigDict


class DocumentOut(BaseModel):
    id: str
    name: str
    category: str

    model_config = ConfigDict(from_attributes=True)


class EvalCaseOut(BaseModel):
    id: str
    input: str
    expected_answer: str
    expected_facts: list[str]
    expected_action: str
    document: DocumentOut


class RunRequest(BaseModel):
    mode: str = "mock"
    case_ids: list[str] | None = None


class EvalResultOut(BaseModel):
    id: int
    case_id: str
    document_name: str
    question: str
    expected_answer: str
    expected_facts: list[str]
    matched_facts: list[str]
    missed_facts: list[str]
    expected_action: str
    answer: str
    action: str
    action_input: str
    answer_match: float
    tool_correct: bool
    hallucination_score: float
    latency_ms: int
    cost_usd: float
    failure_type: str
    passed: bool
    retrieved_chunks: list[str]


class EvalRunOut(BaseModel):
    id: int
    mode: str
    status: str
    total_cases: int
    pass_rate: float
    avg_latency_ms: float
    avg_cost_usd: float
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EvalRunDetail(EvalRunOut):
    results: list[EvalResultOut]


class SummaryOut(BaseModel):
    total_runs: int
    total_tests_run: int
    latest_run: EvalRunOut | None
    pass_rate: float
    avg_latency_ms: float
    avg_cost_usd: float
    failure_counts: dict[str, int]
    failed_cases: list[EvalResultOut]

