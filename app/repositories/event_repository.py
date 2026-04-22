"""Event repository for database operations on payment events."""
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.models import PaymentEvent
from app.repositories.base import BaseRepository
from app.schemas.exceptions import DatabaseError


class EventRepository(BaseRepository):
    """Repository for PaymentEvent model operations."""

    def __init__(self, db: Session):
        super().__init__(db)

    def get_event_by_id(self, event_id: str) -> Optional[PaymentEvent]:
        """
        Get event by event_id (unique index lookup).
        This is critical for idempotency: O(1) lookup via UNIQUE index.
        """
        return self.db.query(PaymentEvent).filter(
            PaymentEvent.event_id == event_id
        ).first()

    def create_event(self, event_id: str, transaction_id: int, event_type: str, timestamp) -> PaymentEvent:
        """
        Create and insert new payment event.
        Raises IntegrityError if event_id already exists (UNIQUE constraint).
        """
        try:
            event = PaymentEvent(
                event_id=event_id,
                transaction_id=transaction_id,
                event_type=event_type,
                timestamp=timestamp
            )
            self.db.add(event)
            self.flush()
            return event
        except IntegrityError:
            self.rollback()
            raise DatabaseError(f"Event with this ID already exists: {event_id}")

    def list_events_by_transaction_id(self, transaction_id: int) -> List[PaymentEvent]:
        """Get all events for a transaction, ordered by timestamp."""
        return self.db.query(PaymentEvent).filter(
            PaymentEvent.transaction_id == transaction_id
        ).order_by(PaymentEvent.timestamp.asc()).all()

    def get_event_count_by_type_for_transaction(
        self, transaction_id: int, event_type: str
    ) -> int:
        """Get count of events of a specific type for a transaction."""
        return self.db.query(PaymentEvent).filter(
            PaymentEvent.transaction_id == transaction_id,
            PaymentEvent.event_type == event_type
        ).count()
