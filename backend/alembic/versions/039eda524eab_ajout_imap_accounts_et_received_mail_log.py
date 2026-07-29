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
    op.create_table(
        "imap_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("imap_host", sa.String(), nullable=False),
        sa.Column("imap_port", sa.Integer(), nullable=False, server_default="993"),
        sa.Column("encrypted_password", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now()),
        sa.UniqueConstraint("email"),
    )

    op.create_table(
        "received_mail_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("imap_account_id", sa.Integer(), sa.ForeignKey("imap_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_uid", sa.String(), nullable=False),
        sa.Column("sender_email", sa.String(), nullable=True),
        sa.Column("subject", sa.String(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("is_seen", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_checked_at", sa.DateTime(timezone=False), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_received_mail_log_account_uid",
        "received_mail_log",
        ["imap_account_id", "message_uid"],
    )


def downgrade() -> None:
    op.drop_index("ix_received_mail_log_account_uid", table_name="received_mail_log")
    op.drop_table("received_mail_log")
    op.drop_table("imap_accounts")