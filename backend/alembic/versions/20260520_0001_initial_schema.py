"""initial schema

Revision ID: 20260520_0001
Revises:
Create Date: 2026-05-20
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260520_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
    )
    op.create_table(
        "eval_cases",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("document_id", sa.String(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("input", sa.Text(), nullable=False),
        sa.Column("expected_answer", sa.Text(), nullable=False),
        sa.Column("expected_facts_json", sa.Text(), nullable=False),
        sa.Column("expected_action", sa.String(), nullable=False),
        sa.Column("acceptable_actions_json", sa.Text(), nullable=False, server_default="[]"),
    )
    op.create_table(
        "eval_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False, server_default="mock"),
        sa.Column("model", sa.String(), nullable=False, server_default="mock-deterministic"),
        sa.Column("judge_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(), nullable=False, server_default="completed"),
        sa.Column("total_cases", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pass_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("avg_latency_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("avg_cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "eval_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("eval_runs.id"), nullable=False),
        sa.Column("case_id", sa.String(), sa.ForeignKey("eval_cases.id"), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("action_input", sa.Text(), nullable=False, server_default=""),
        sa.Column("answer_match", sa.Float(), nullable=False),
        sa.Column("fact_recall", sa.Float(), nullable=False, server_default="0"),
        sa.Column("fact_precision", sa.Float(), nullable=False, server_default="0"),
        sa.Column("tool_correct", sa.Boolean(), nullable=False),
        sa.Column("action_input_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("retrieval_hit", sa.Float(), nullable=False, server_default="0"),
        sa.Column("groundedness", sa.Float(), nullable=False, server_default="0"),
        sa.Column("schema_valid", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("judge_score", sa.Float(), nullable=True),
        sa.Column("hallucination_score", sa.Float(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("failure_type", sa.String(), nullable=False),
        sa.Column("failure_mode", sa.String(), nullable=False, server_default="none"),
        sa.Column("failure_explanation", sa.Text(), nullable=False, server_default=""),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("retrieved_chunks_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("unsupported_claims_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("trace_json", sa.Text(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_table("eval_results")
    op.drop_table("eval_runs")
    op.drop_table("eval_cases")
    op.drop_table("documents")
