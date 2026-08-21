"""Phase 4 models update

Revision ID: 023
Revises: 022
Create Date: 2026-08-20 21:34:37.748233

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "023"
down_revision: Union[str, Sequence[str], None] = "022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    from sqlalchemy.engine.reflection import Inspector

    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)

    events_cols = [col["name"] for col in inspector.get_columns("events")]
    if "deleted_at" not in events_cols:
        op.add_column("events", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    rooms_cols = [col["name"] for col in inspector.get_columns("rooms")]
    if "eventyay_room_id" not in rooms_cols:
        op.add_column("rooms", sa.Column("eventyay_room_id", sa.String(length=255), nullable=True))

    indexes = [idx["name"] for idx in inspector.get_indexes("rooms")]
    if "uq_room_event_eventyay_id" not in indexes:
        op.create_index("uq_room_event_eventyay_id", "rooms", ["event_id", "eventyay_room_id"], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("uq_room_event_eventyay_id", table_name="rooms")
    op.drop_column("rooms", "eventyay_room_id")
    op.drop_column("events", "deleted_at")
