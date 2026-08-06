"""ajout colonnes manquantes received_mail_log

Revision ID: 77c15847f7cd
Revises: e694273d7b57
Create Date: 2026-08-06 12:00:08.592840

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = '77c15847f7cd'
down_revision: Union[str, Sequence[str], None] = 'e694273d7b57'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass