"""index 

Revision ID: d6855d56a71d
Revises: 3ea076d2a692
Create Date: 2026-08-12 02:15:04.507825

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd6855d56a71d'
down_revision: Union[str, Sequence[str], None] = '3ea076d2a692'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(inspector, table, column):
    return column in [c["name"] for c in inspector.get_columns(table)]


def _has_index(inspector, table, index_name):
    return index_name in [i["name"] for i in inspector.get_indexes(table)]


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if not _has_index(inspector, 'email_log', 'ix_email_log_opened_at'):
        op.create_index(op.f('ix_email_log_opened_at'), 'email_log', ['opened_at'], unique=False)
    if not _has_index(inspector, 'email_log', 'ix_email_log_sender_email'):
        op.create_index(op.f('ix_email_log_sender_email'), 'email_log', ['sender_email'], unique=False)
    if not _has_index(inspector, 'email_log', 'ix_email_log_sent_at'):
        op.create_index(op.f('ix_email_log_sent_at'), 'email_log', ['sent_at'], unique=False)

    if _has_column(inspector, 'email_log', 'direction'):
        op.drop_column('email_log', 'direction')

    if _has_column(inspector, 'imap_accounts', 'uid_validity'):
        op.drop_column('imap_accounts', 'uid_validity')

    if _has_index(inspector, 'received_mail_log', 'ix_received_mail_log_account_uid_validity'):
        op.drop_index(op.f('ix_received_mail_log_account_uid_validity'), table_name='received_mail_log')

    if not _has_index(inspector, 'received_mail_log', 'ix_received_mail_log_imap_account_id'):
        op.create_index(op.f('ix_received_mail_log_imap_account_id'), 'received_mail_log', ['imap_account_id'], unique=False)
    if not _has_index(inspector, 'received_mail_log', 'ix_received_mail_log_received_at'):
        op.create_index(op.f('ix_received_mail_log_received_at'), 'received_mail_log', ['received_at'], unique=False)
    if not _has_index(inspector, 'received_mail_log', 'ix_received_mail_log_sender_email'):
        op.create_index(op.f('ix_received_mail_log_sender_email'), 'received_mail_log', ['sender_email'], unique=False)

    if _has_column(inspector, 'received_mail_log', 'uid_validity'):
        op.drop_column('received_mail_log', 'uid_validity')


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if not _has_column(inspector, 'received_mail_log', 'uid_validity'):
        op.add_column('received_mail_log', sa.Column('uid_validity', sa.VARCHAR(), autoincrement=False, nullable=True))

    if _has_index(inspector, 'received_mail_log', 'ix_received_mail_log_sender_email'):
        op.drop_index(op.f('ix_received_mail_log_sender_email'), table_name='received_mail_log')
    if _has_index(inspector, 'received_mail_log', 'ix_received_mail_log_received_at'):
        op.drop_index(op.f('ix_received_mail_log_received_at'), table_name='received_mail_log')
    if _has_index(inspector, 'received_mail_log', 'ix_received_mail_log_imap_account_id'):
        op.drop_index(op.f('ix_received_mail_log_imap_account_id'), table_name='received_mail_log')

    if not _has_index(inspector, 'received_mail_log', 'ix_received_mail_log_account_uid_validity'):
        op.create_index(op.f('ix_received_mail_log_account_uid_validity'), 'received_mail_log', ['imap_account_id', 'message_uid', 'uid_validity'], unique=False)

    if not _has_column(inspector, 'imap_accounts', 'uid_validity'):
        op.add_column('imap_accounts', sa.Column('uid_validity', sa.VARCHAR(), autoincrement=False, nullable=True))

    if not _has_column(inspector, 'email_log', 'direction'):
        op.add_column('email_log', sa.Column('direction', sa.VARCHAR(length=10), server_default=sa.text("'sent'::character varying"), autoincrement=False, nullable=False))

    if _has_index(inspector, 'email_log', 'ix_email_log_sent_at'):
        op.drop_index(op.f('ix_email_log_sent_at'), table_name='email_log')
    if _has_index(inspector, 'email_log', 'ix_email_log_sender_email'):
        op.drop_index(op.f('ix_email_log_sender_email'), table_name='email_log')
    if _has_index(inspector, 'email_log', 'ix_email_log_opened_at'):
        op.drop_index(op.f('ix_email_log_opened_at'), table_name='email_log')