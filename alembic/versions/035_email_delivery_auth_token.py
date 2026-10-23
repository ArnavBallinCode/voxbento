"""Suppress queued links once their authentication token is invalid.

Revision ID: 035
Revises: 034
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "email_deliveries",
        sa.Column("auth_token_id", sa.Integer(), sa.ForeignKey("auth_tokens.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_email_deliveries_auth_token_id", "email_deliveries", ["auth_token_id"])


def downgrade() -> None:
    op.drop_index("ix_email_deliveries_auth_token_id", table_name="email_deliveries")
    op.drop_column("email_deliveries", "auth_token_id")
