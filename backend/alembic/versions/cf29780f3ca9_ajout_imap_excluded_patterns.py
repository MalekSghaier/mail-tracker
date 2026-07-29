"""ajout imap_excluded_patterns

Revision ID: cf29780f3ca9
Revises: 303e85031398
Create Date: 2026-07-27 10:45:33.101160

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cf29780f3ca9'
down_revision: Union[str, Sequence[str], None] = '303e85031398'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "imap_excluded_patterns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pattern", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now()),
        sa.UniqueConstraint("pattern"),
    )


def downgrade() -> None:
    op.drop_table("imap_excluded_patterns")
