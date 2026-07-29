"""retire imap_host et imap_port de imap_accounts

Revision ID: 303e85031398
Revises: 039eda524eab
Create Date: 2026-07-27 10:01:11.230946

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '303e85031398'
down_revision: Union[str, Sequence[str], None] = '039eda524eab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("imap_accounts", "imap_host")
    op.drop_column("imap_accounts", "imap_port")


def downgrade() -> None:
    op.add_column("imap_accounts", sa.Column("imap_host", sa.String(), nullable=True))
    op.add_column("imap_accounts", sa.Column("imap_port", sa.Integer(), nullable=True, server_default="993"))
