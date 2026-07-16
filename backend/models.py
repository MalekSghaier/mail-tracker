"""
Modèles SQLAlchemy — reflètent le schéma Postgres existant (voir M8).
"""
import uuid
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from db import Base


class Admin(Base):
    __tablename__ = "admins"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    is_active = Column(Boolean, default=True, nullable=False)


class AppUser(Base):
    __tablename__ = "app_users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    email = Column(String, nullable=True)
    password_hash = Column(String, nullable=False)
    department = Column(String, nullable=True)
    account_role = Column(String, nullable=False, default="employee")
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    created_by_admin_id = Column(Integer, ForeignKey("admins.id"), nullable=True)


class EmailLog(Base):
    __tablename__ = "email_log"

    tracking_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sender_email = Column(String, nullable=False)
    recipient_email = Column(String, nullable=False)
    cc_email = Column(String, nullable=True)
    subject = Column(String, nullable=True)
    body = Column(Text, nullable=True)
    ai_summary = Column(Text, nullable=True)
    sent_at = Column(DateTime(timezone=False), server_default=func.now())
    opened_at = Column(DateTime(timezone=False), nullable=True)
    alert_acked = Column(Boolean, default=False, nullable=False)
    reminder_done = Column(Boolean, nullable=True)
    reminder_answered_at = Column(DateTime(timezone=False), nullable=True)
    reminder_recheck_at = Column(DateTime(timezone=False), nullable=True)



class Session(Base):
    __tablename__ = "sessions"
    id = Column(Integer, primary_key=True)
    token_hash = Column(String(64), unique=True, nullable=False)
    role = Column(String(20), nullable=False)
    subject = Column(String(255), nullable=False)
    admin_id = Column(Integer, ForeignKey("admins.id", ondelete="CASCADE"), nullable=True)
    user_id = Column(Integer, ForeignKey("app_users.id", ondelete="CASCADE"), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    __table_args__ = (
        Index("idx_sessions_token_hash", "token_hash"),
    )