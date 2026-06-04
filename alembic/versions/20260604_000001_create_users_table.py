"""create users table

Revision ID: 20260604_000001
Revises:
Create Date: 2026-06-04 12:00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260604_000001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("telegram_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("telegram_tag", sa.String(length=64), nullable=True),
        sa.Column("telegram_channel_url", sa.String(length=255), nullable=True),
        sa.Column("name_style", sa.Text(), nullable=False, server_default=sa.text("'{me}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("telegram_id"),
    )

    op.alter_column("users", "name_style", server_default=None)


def downgrade() -> None:
    op.drop_table("users")
