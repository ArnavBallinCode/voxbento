"""Let organizers hide the speaker's captions from listeners while AI still translates them.

Revision ID: 036
Revises: 035
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("rooms") as batch_op:
        batch_op.add_column(sa.Column("floor_captions_visible", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    with op.batch_alter_table("rooms") as batch_op:
        batch_op.drop_column("floor_captions_visible")
