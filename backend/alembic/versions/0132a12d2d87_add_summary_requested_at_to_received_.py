"""add summary_requested_at to received_mail_log

Revision ID: 0132a12d2d87
Revises: d6855d56a71d
Create Date: 2026-08-13 12:35:05.403848

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0132a12d2d87'
down_revision: Union[str, Sequence[str], None] = 'd6855d56a71d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column('received_mail_log', sa.Column('summary_requested_at', sa.DateTime(), nullable=True))

def downgrade():
    op.drop_column('received_mail_log', 'summary_requested_at')
