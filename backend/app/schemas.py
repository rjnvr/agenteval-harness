from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


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
    required_facts: list[str]
    supporting_facts: list[str]
    expected_action: str
    acceptable_actions: list[str]
    document: DocumentOut


class RunRequest(BaseModel):
    provider: str = "mock"
    model: str | None = None
    case_ids: list[str] | None = None
    api_key: str | None = Field(default=None, repr=False)
    judge_enabled: bool = False
    mode: str | None = None


class EvalResultOut(BaseModel):
    id: int
    case_id: str
    document_name: str
    question: str
    expected_answer: str
    expected_facts: list[str]
    required_facts: list[str]
    supporting_facts: list[str]
    matched_facts: list[str]
    missed_facts: list[str]
    expected_action: str
    acceptable_actions: list[str]
    answer: str
    action: str
    action_input: str
    answer_match: float
    fact_recall: float
    fact_precision: float
    tool_correct: bool
    action_input_score: float
    retrieval_hit: float
    groundedness: float
    schema_valid: bool
    judge_score: float | None
    hallucination_score: float
    unsupported_claims: list[str]
    latency_ms: int
    cost_usd: float
    failure_type: str
    failure_mode: str
    failure_explanation: str
    passed: bool
    retrieved_chunks: list[str]
    trace: dict[str, object]


class EvalRunOut(BaseModel):
    id: int
    mode: str
    provider: str
    model: str
    judge_enabled: bool
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
    calibration: dict[str, object]
    pii_redaction: dict[str, object]
