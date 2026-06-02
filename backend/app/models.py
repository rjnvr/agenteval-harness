from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.database import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    cases: Mapped[list["EvalCase"]] = relationship(back_populates="document")


class EvalCase(Base):
    __tablename__ = "eval_cases"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), nullable=False)
    input: Mapped[str] = mapped_column(Text, nullable=False)
    expected_answer: Mapped[str] = mapped_column(Text, nullable=False)
    expected_facts_json: Mapped[str] = mapped_column(Text, nullable=False)
    expected_action: Mapped[str] = mapped_column(String, nullable=False)
    acceptable_actions_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    context_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    expected_decision_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    document: Mapped[Document] = relationship(back_populates="cases")


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mode: Mapped[str] = mapped_column(String, nullable=False)
    provider: Mapped[str] = mapped_column(String, default="mock", nullable=False)
    model: Mapped[str] = mapped_column(String, default="mock-deterministic", nullable=False)
    judge_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String, default="completed", nullable=False)
    total_cases: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pass_rate: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    avg_latency_ms: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    avg_cost_usd: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    results: Mapped[list["EvalResult"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class EvalResult(Base):
    __tablename__ = "eval_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("eval_runs.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(ForeignKey("eval_cases.id"), nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    action_input: Mapped[str] = mapped_column(Text, default="", nullable=False)
    answer_match: Mapped[float] = mapped_column(Float, nullable=False)
    fact_recall: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    fact_precision: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    tool_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    action_input_score: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    retrieval_hit: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    groundedness: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    schema_valid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    judge_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    hallucination_score: Mapped[float] = mapped_column(Float, nullable=False)
    slot_valid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    preference_score: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    timezone_correct: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    proposed_slot: Mapped[str] = mapped_column(Text, default="", nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False)
    failure_type: Mapped[str] = mapped_column(String, nullable=False)
    failure_mode: Mapped[str] = mapped_column(String, default="none", nullable=False)
    failure_explanation: Mapped[str] = mapped_column(Text, default="", nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    retrieved_chunks_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    unsupported_claims_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    trace_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    run: Mapped[EvalRun] = relationship(back_populates="results")
    case: Mapped[EvalCase] = relationship()
