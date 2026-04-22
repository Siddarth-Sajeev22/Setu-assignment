"""SQLAlchemy ORM models for payment transactions and events."""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Numeric, DateTime, ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship
from app.database import Base
import enum


class PaymentStatus(str, enum.Enum):
    """Payment status enumeration."""
    INITIATED = "initiated"
    PROCESSED = "processed"
    FAILED = "failed"
    SETTLED = "settled"


class Merchant(Base):
    """Merchant model."""
    __tablename__ = "merchants"

    id = Column(Integer, primary_key=True)
    merchant_id = Column(String(100), unique=True, nullable=False)  # unique already creates index
    merchant_name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    transactions = relationship("Transaction", back_populates="merchant")

    def __repr__(self):
        return f"<Merchant(id={self.id}, merchant_id={self.merchant_id}, merchant_name={self.merchant_name})>"


class Transaction(Base):
    """Transaction model."""
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True)
    transaction_id = Column(String(36), unique=True, nullable=False)  # unique already creates index
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False, index=True)
    amount = Column(Numeric(15, 2), nullable=False)
    currency = Column(String(3), nullable=False)
    status = Column(String(20), nullable=False, index=True, default=PaymentStatus.INITIATED)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    merchant = relationship("Merchant", back_populates="transactions")
    events = relationship(
        "PaymentEvent",
        back_populates="transaction",
        cascade="all, delete-orphan",
        order_by="PaymentEvent.timestamp",
    )

    __table_args__ = (
        Index("idx_transaction_merchant_status", "merchant_id", "status"),
        Index("idx_transaction_created_status", "created_at", "status"),
    )

    def __repr__(self):
        return f"<Transaction(id={self.id}, transaction_id={self.transaction_id}, status={self.status})>"


class PaymentEvent(Base):
    """Payment event model for storing event history."""
    __tablename__ = "payment_events"

    id = Column(Integer, primary_key=True)
    event_id = Column(String(36), unique=True, nullable=False)  # unique already creates index
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=False, index=True)
    event_type = Column(String(20), nullable=False)
    timestamp = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    transaction = relationship("Transaction", back_populates="events")

    # Composite index: discrepancy queries filter on both columns together
    __table_args__ = (
        Index("idx_payment_events_transaction_event_type", "transaction_id", "event_type"),
    )

    def __repr__(self):
        return f"<PaymentEvent(id={self.id}, event_id={self.event_id}, event_type={self.event_type})>"
