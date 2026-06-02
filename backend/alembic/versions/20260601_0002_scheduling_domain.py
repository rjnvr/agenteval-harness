"""scheduling domain fields

Revision ID: 20260601_0002
Revises: 20260520_0001
Create Date: 2026-06-01
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260601_0002"
down_revision: str | Sequence[str] | None = "20260520_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("eval_cases", sa.Column("context_json", sa.Text(), nullable=False, server_default="{}"))
    op.add_column("eval_cases", sa.Column("expected_decision_json", sa.Text(), nullable=False, server_default="{}"))
    op.add_column("eval_results", sa.Column("slot_valid", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("eval_results", sa.Column("preference_score", sa.Float(), nullable=False, server_default="1"))
    op.add_column("eval_results", sa.Column("timezone_correct", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("eval_results", sa.Column("proposed_slot", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("eval_results", "proposed_slot")
    op.drop_column("eval_results", "timezone_correct")
    op.drop_column("eval_results", "preference_score")
    op.drop_column("eval_results", "slot_valid")
    op.drop_column("eval_cases", "expected_decision_json")
    op.drop_column("eval_cases", "context_json")
