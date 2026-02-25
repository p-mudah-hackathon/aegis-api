"""
SQLAlchemy ORM models — Transaction, AttackRun, FraudReason, ChatSession, ChatMessage.
"""
import datetime
import uuid
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, JSON,
)
from sqlalchemy.orm import relationship
from database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Transaction(Base):
    """A single scored transaction."""
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    txn_id = Column(String(32), unique=True, nullable=False, index=True)
    timestamp = Column(String(32), nullable=False)
    payer = Column(String(64), nullable=False, index=True)
    issuer = Column(String(32), nullable=False)
    country = Column(String(8), nullable=False)
    merchant = Column(String(128), nullable=False, index=True)
    city = Column(String(64), nullable=False)
    amount_idr = Column(Integer, nullable=False)
    amount_foreign = Column(Float, nullable=False)
    currency = Column(String(8), nullable=False)
    risk_score = Column(Float, nullable=False, index=True)
    is_flagged = Column(Boolean, nullable=False, default=False)
    is_fraud = Column(Boolean, nullable=False, default=False)
    fraud_type = Column(String(32), nullable=True, index=True)
    attack_detail = Column(Text, nullable=True)
    xai_reasons = Column(JSON, nullable=True)

    # Analyst review
    review_status = Column(
        String(20), nullable=True, index=True,
        comment="confirmed_fraud | false_positive | pending | null",
    )
    reviewed_at = Column(DateTime, nullable=True)
    review_note = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    fraud_reason = relationship("FraudReason", back_populates="transaction", uselist=False)
    chat_sessions = relationship("ChatSession", back_populates="transaction")


class SimulatedTransaction(Base):
    """A single scored transaction from an attack simulation."""
    __tablename__ = "simulated_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    txn_id = Column(String(32), unique=True, nullable=False, index=True)
    timestamp = Column(String(32), nullable=False)
    payer = Column(String(64), nullable=False, index=True)
    issuer = Column(String(32), nullable=False)
    country = Column(String(8), nullable=False)
    merchant = Column(String(128), nullable=False, index=True)
    city = Column(String(64), nullable=False)
    amount_idr = Column(Integer, nullable=False)
    amount_foreign = Column(Float, nullable=False)
    currency = Column(String(8), nullable=False)
    risk_score = Column(Float, nullable=False, index=True)
    is_flagged = Column(Boolean, nullable=False, default=False)
    is_fraud = Column(Boolean, nullable=False, default=False)
    fraud_type = Column(String(32), nullable=True, index=True)
    attack_detail = Column(Text, nullable=True)
    xai_reasons = Column(JSON, nullable=True)

    # Analyst review
    review_status = Column(
        String(20), nullable=True, index=True,
        comment="confirmed_fraud | false_positive | pending | null",
    )
    reviewed_at = Column(DateTime, nullable=True)
    review_note = Column(Text, nullable=True)

    # Link to attack run
    attack_run_id = Column(Integer, ForeignKey("attack_runs.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    attack_run = relationship("AttackRun", back_populates="transactions")


class AttackRun(Base):
    """A single attack simulation run."""
    __tablename__ = "attack_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    total_txns = Column(Integer, nullable=False)
    fraud_pct = Column(Float, nullable=False)
    speed = Column(String(16), nullable=False)
    mode = Column(String(16), nullable=True)

    # Results
    total = Column(Integer, default=0)
    approved = Column(Integer, default=0)
    flagged = Column(Integer, default=0)
    tp = Column(Integer, default=0)
    fp = Column(Integer, default=0)
    tn = Column(Integer, default=0)
    fn = Column(Integer, default=0)
    recall = Column(Float, default=0)
    precision_ = Column("precision", Float, default=0)
    f1 = Column(Float, default=0)
    fpr = Column(Float, default=0)
    roi_saved = Column(Integer, default=0)
    per_type = Column(JSON, default=dict)
    per_type_total = Column(JSON, default=dict)

    status = Column(
        String(16), default="running", index=True,
        comment="running | completed | failed",
    )

    started_at = Column(DateTime, default=datetime.datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    transactions = relationship("SimulatedTransaction", back_populates="attack_run")


class FraudReason(Base):
    """Cached Qwen AI fraud reasoning for a transaction."""
    __tablename__ = "fraud_reasons"

    id = Column(Integer, primary_key=True, autoincrement=True)
    txn_id = Column(String(32), ForeignKey("transactions.txn_id"), unique=True, nullable=False)
    risk_score = Column(Float)
    fraud_type = Column(String(32), nullable=True)
    reasoning = Column(Text, nullable=False)
    explanation = Column(Text, nullable=False)
    confidence = Column(String(8), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    transaction = relationship("Transaction", back_populates="fraud_reason")


class ChatSession(Base):
    """A chat session about a specific flagged transaction."""
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(String(36), unique=True, nullable=False, index=True, default=_uuid)
    txn_id = Column(String(32), ForeignKey("transactions.txn_id"), nullable=False, index=True)
    title = Column(String(256), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    # Relationships
    transaction = relationship("Transaction", back_populates="chat_sessions")
    messages = relationship("ChatMessage", back_populates="session", order_by="ChatMessage.seq")


class ChatMessage(Base):
    """A single message in a chat session."""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(String(36), ForeignKey("chat_sessions.chat_id"), nullable=False, index=True)
    seq = Column(Integer, nullable=False, comment="Message sequence number within the chat")
    role = Column(String(16), nullable=False, comment="system | user | assistant")
    content = Column(Text, nullable=False)
    reasoning = Column(Text, nullable=True, comment="AI thinking/reasoning (if thinking mode)")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    session = relationship("ChatSession", back_populates="messages")
