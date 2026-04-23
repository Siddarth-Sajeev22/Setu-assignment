"""API router for payment event ingestion."""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.requests import EventPayloadRequest
from app.schemas.responses import EventResponse, ErrorResponse
from app.schemas.exceptions import APIException
from app.services.event_processor import EventProcessor

router = APIRouter(prefix="/events", tags=["events"])


@router.post(
    "",
    response_model=EventResponse,
    status_code=201,
    responses={
        201: {"description": "Event ingested successfully"},
        200: {"description": "Event already exists (idempotent)"},
        400: {"description": "Invalid event payload"},
    }
)
def ingest_event(
    request: EventPayloadRequest,
    http_response: Response,
    db: Session = Depends(get_db)
):
    """
    Ingest a payment lifecycle event.

    Events are idempotent: submitting the same event_id multiple times
    returns 200 with the existing record without creating duplicates.

    Accepted event types:
    - payment_initiated: Transaction initiated
    - payment_processed: Payment successfully processed
    - payment_failed: Payment processing failed
    - settled: Payment settled
    """
    try:
        processor = EventProcessor(db)
        event, status_code = processor.process_event(request)

        if status_code == 200:
            http_response.status_code = 200

        return EventResponse.model_validate({
            "id": event.id,
            "event_id": event.event_id,
            "transaction_id": request.transaction_id,
            "event_type": event.event_type,
            "timestamp": event.timestamp,
            "created_at": event.created_at,
        })

    except APIException as e:
        raise HTTPException(status_code=e.status_code, detail=str(e.message))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
