"""Persist conversation messages."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261005_03"
down_revision: Union[str, None] = "20261005_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("messages", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("conversations", "messages")
