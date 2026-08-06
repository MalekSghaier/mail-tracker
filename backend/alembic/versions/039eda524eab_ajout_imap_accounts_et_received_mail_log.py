"""ajout imap_accounts et received_mail_log

Revision ID: 039eda524eab
Revises: c8f196c312a3
Create Date: 2026-07-22 13:30:36.738449
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '039eda524eab'
down_revision: Union[str, Sequence[str], None] = 'c8f196c312a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass