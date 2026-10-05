"""Create user-owned conversations."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261005_02"
down_revision: Union[str, None] = "20261005_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_conversations_user_id", table_name="conversations")
    op.drop_table("conversations")
