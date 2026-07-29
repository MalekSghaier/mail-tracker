"""lie imap_accounts a app_users

Revision ID: e694273d7b57
Revises: cf29780f3ca9
Create Date: 2026-07-27 13:36:47.783915

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e694273d7b57'
down_revision: Union[str, Sequence[str], None] = 'cf29780f3ca9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("imap_accounts", sa.Column("app_user_id", sa.Integer(), sa.ForeignKey("app_users.id", ondelete="CASCADE"), nullable=True))


def downgrade() -> None:
    op.drop_column("imap_accounts", "app_user_id")
