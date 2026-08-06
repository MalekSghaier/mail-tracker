"""baseline schema existant

Revision ID: c8f196c312a3
Revises: 
Create Date: 2026-07-15 15:19:12.888096

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c8f196c312a3'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('admins',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(), nullable=False),
    sa.Column('password_hash', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('username')
    )
    op.create_table('email_log',
    sa.Column('tracking_id', sa.UUID(), nullable=False),
    sa.Column('sender_email', sa.String(), nullable=False),
    sa.Column('recipient_email', sa.String(), nullable=False),
    sa.Column('cc_email', sa.String(), nullable=True),
    sa.Column('subject', sa.String(), nullable=True),
    sa.Column('body', sa.Text(), nullable=True),
    sa.Column('ai_summary', sa.Text(), nullable=True),
    sa.Column('sent_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.Column('opened_at', sa.DateTime(), nullable=True),
    sa.Column('alert_acked', sa.Boolean(), nullable=False),
    sa.Column('reminder_done', sa.Boolean(), nullable=True),
    sa.Column('reminder_answered_at', sa.DateTime(), nullable=True),
    sa.Column('reminder_recheck_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('tracking_id')
    )
    op.create_table('imap_excluded_patterns',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('pattern', sa.String(), nullable=False),
    sa.Column('description', sa.String(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('pattern')
    )
    op.create_table('app_users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(), nullable=False),
    sa.Column('email', sa.String(), nullable=True),
    sa.Column('password_hash', sa.String(), nullable=False),
    sa.Column('department', sa.String(), nullable=True),
    sa.Column('account_role', sa.String(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('created_by_admin_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['created_by_admin_id'], ['admins.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('username')
    )
    op.create_table('imap_accounts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('label', sa.String(), nullable=False),
    sa.Column('email', sa.String(), nullable=False),
    sa.Column('encrypted_password', sa.Text(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.Column('app_user_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['app_user_id'], ['app_users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    op.create_table('sessions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('subject', sa.String(length=255), nullable=False),
    sa.Column('admin_id', sa.Integer(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['admin_id'], ['admins.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['app_users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    op.create_index('idx_sessions_token_hash', 'sessions', ['token_hash'], unique=False)
    op.create_table('received_mail_log',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tracking_id', sa.UUID(), nullable=False),
    sa.Column('imap_account_id', sa.Integer(), nullable=False),
    sa.Column('message_uid', sa.String(), nullable=False),
    sa.Column('sender_email', sa.String(), nullable=True),
    sa.Column('cc_email', sa.String(), nullable=True),
    sa.Column('subject', sa.String(), nullable=True),
    sa.Column('body', sa.Text(), nullable=True),
    sa.Column('ai_summary', sa.Text(), nullable=True),
    sa.Column('received_at', sa.DateTime(), nullable=True),
    sa.Column('is_seen', sa.Boolean(), nullable=False),
    sa.Column('last_checked_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.Column('supervisor_acked', sa.Boolean(), nullable=False),
    sa.Column('reminder_done', sa.Boolean(), nullable=True),
    sa.Column('reminder_answered_at', sa.DateTime(), nullable=True),
    sa.Column('reminder_recheck_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['imap_account_id'], ['imap_accounts.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('tracking_id')
    )


def downgrade() -> None:
    op.drop_table('received_mail_log')
    op.drop_index('idx_sessions_token_hash', table_name='sessions')
    op.drop_table('sessions')
    op.drop_table('imap_accounts')
    op.drop_table('app_users')
    op.drop_table('imap_excluded_patterns')
    op.drop_table('email_log')
    op.drop_table('admins')