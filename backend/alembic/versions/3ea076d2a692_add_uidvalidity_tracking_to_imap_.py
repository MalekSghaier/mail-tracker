"""add uidvalidity tracking to imap accounts and received mail log

Revision ID: 3ea076d2a692
Revises: 77c15847f7cd
Create Date: 2026-08-06 15:10:17.993472

"""
from alembic import op
import sqlalchemy as sa

revision = "3ea076d2a692"
down_revision = "77c15847f7cd"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("imap_accounts", sa.Column("last_uidvalidity", sa.BigInteger(), nullable=True))
    op.add_column("received_mail_log", sa.Column("uidvalidity", sa.BigInteger(), nullable=True))
    op.create_index(
        "idx_received_mail_account_uid_uidval",
        "received_mail_log",
        ["imap_account_id", "message_uid", "uidvalidity"],
    )


def downgrade():
    op.drop_index("idx_received_mail_account_uid_uidval", table_name="received_mail_log")
    op.drop_column("received_mail_log", "uidvalidity")
    op.drop_column("imap_accounts", "last_uidvalidity")

