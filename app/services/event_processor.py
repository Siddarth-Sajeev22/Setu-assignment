"""Event processor service with three-layer idempotency."""
from typing import Tuple
from sqlalchemy.orm import Session
from app.models import PaymentEvent
from app.schemas.requests import EventPayloadRequest
from app.schemas.exceptions import ValidationError, DatabaseError
from app.repositories.merchant_repository import MerchantRepository
from app.repositories.transaction_repository import TransactionRepository
from app.repositories.event_repository import EventRepository


class EventProcessor:
    """
    Service to process payment events with perfect idempotency.
    
    Three-layer idempotency:
    1. Pydantic validation (request schema validates types, enums, ranges)
    2. Business logic check (query event_id index for duplicates)
    3. DB UNIQUE constraint (safety net for race conditions)
    """

    # State machine: allowed transitions
    STATE_TRANSITIONS = {
        "initiated": ["processed", "failed"],  # initiated can go to processed or failed
        "processed": ["settled"],  # processed can only go to settled
        "failed": [],  # failed is terminal
        "settled": [],  # settled is terminal
    }

    def __init__(self, db: Session):
        self.db = db
        self.merchant_repo = MerchantRepository(db)
        self.transaction_repo = TransactionRepository(db)
        self.event_repo = EventRepository(db)

    def process_event(self, request: EventPayloadRequest) -> Tuple[PaymentEvent, int]:
        """
        Process incoming event with three-layer idempotency.

        Returns: (event, status_code) — 201 for new event, 200 for duplicate.
        """
        # ===== LAYER 1: Pydantic validation (already done by FastAPI) =====
        # Request schema validates: event_id (UUID), transaction_id (UUID),
        # merchant_id (non-empty), event_type (enum), amount (> 0), currency, timestamp

        # ===== LAYER 2: Business logic idempotency check =====
        # Query event_id with UNIQUE index (O(1) lookup)
        existing_event = self.event_repo.get_event_by_id(request.event_id)

        if existing_event:
            return (existing_event, 200)

        # ===== LAYER 2b: Business logic - state machine validation =====
        # Get or create merchant
        merchant = self.merchant_repo.get_or_create_merchant(
            merchant_id=request.merchant_id,
            merchant_name=request.merchant_name
        )

        # Get existing transaction or prepare to create
        transaction = self.transaction_repo.get_by_transaction_id(request.transaction_id)

        # Map event_type to status
        event_type_to_status = {
            "payment_initiated": "initiated",
            "payment_processed": "processed",
            "payment_failed": "failed",
            "settled": "settled",
        }
        new_status = event_type_to_status[request.event_type]

        if transaction:
            # Validate state transition
            current_status = transaction.status
            allowed_next_states = self.STATE_TRANSITIONS.get(current_status, [])

            if new_status not in allowed_next_states:
                raise ValidationError(
                    f"Invalid state transition: {current_status} -> {new_status}",
                    detail=f"From status '{current_status}', allowed transitions are: {allowed_next_states}"
                )
        else:
            # First event for this transaction - must be "initiated"
            if new_status != "initiated":
                raise ValidationError(
                    f"First event for transaction must be 'payment_initiated', got '{request.event_type}'",
                    detail="New transactions must start with payment_initiated event"
                )

        # ===== LAYER 3: Create event and update transaction in DB =====
        # This also validates UNIQUE(event_id) constraint at DB level
        try:
            # Create transaction if doesn't exist
            if not transaction:
                transaction = self.transaction_repo.create_transaction(
                    transaction_id=request.transaction_id,
                    merchant_id=merchant.id,
                    amount=request.amount,
                    currency=request.currency,
                    status=new_status
                )
            else:
                # Update existing transaction status
                transaction = self.transaction_repo.update_transaction_status(
                    transaction_id=transaction.id,
                    status=new_status
                )

            # Create payment event
            event = self.event_repo.create_event(
                event_id=request.event_id,
                transaction_id=transaction.id,
                event_type=request.event_type,
                timestamp=request.timestamp
            )

            # Commit transaction
            self.transaction_repo.commit()

            return (event, 201)

        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Failed to process event: {str(e)}")

