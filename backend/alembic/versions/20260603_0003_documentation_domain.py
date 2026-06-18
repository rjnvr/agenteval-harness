"""documentation domain fields

Revision ID: 20260603_0003
Revises: 20260601_0002
Create Date: 2026-06-03
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260603_0003"
down_revision: str | Sequence[str] | None = "20260601_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("eval_cases", sa.Column("domain", sa.String(), nullable=False, server_default="scheduling"))
    op.add_column("eval_runs", sa.Column("domain", sa.String(), nullable=False, server_default="scheduling"))
    op.add_column("eval_results", sa.Column("context_precision", sa.Float(), nullable=False, server_default="0"))
    op.add_column("eval_results", sa.Column("citation_score", sa.Float(), nullable=False, server_default="0"))
    op.add_column("eval_results", sa.Column("refusal_correct", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("eval_results", sa.Column("citations_json", sa.Text(), nullable=False, server_default="[]"))


def downgrade() -> None:
    op.drop_column("eval_results", "citations_json")
    op.drop_column("eval_results", "refusal_correct")
    op.drop_column("eval_results", "citation_score")
    op.drop_column("eval_results", "context_precision")
    op.drop_column("eval_runs", "domain")
    op.drop_column("eval_cases", "domain")
