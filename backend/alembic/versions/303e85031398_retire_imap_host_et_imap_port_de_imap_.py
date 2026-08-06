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
    pass


def downgrade() -> None:
    pass
