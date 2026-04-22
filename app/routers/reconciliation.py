"""API router for reconciliation queries."""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from datetime import datetime
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.responses import ReconciliationSummaryResponse, DiscrepancyResponse
from app.schemas.exceptions import APIException
from app.services.reconciliation import ReconciliationService

router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])


@router.get(
    "/summary",
    response_model=ReconciliationSummaryResponse,
    responses={
        200: {"description": "Reconciliation summary"},
        400: {"description": "Invalid filter parameters"},
    }
)
def get_reconciliation_summary(
    merchant_id: Optional[str] = Query(None, description="Filter by merchant ID"),
    start_date: Optional[datetime] = Query(None, description="Start date for filtering"),
    end_date: Optional[datetime] = Query(None, description="End date for filtering"),
    group_by: str = Query("merchant", description="Dimension to group by"),
    db: Session = Depends(get_db)
):
    """
    Get reconciliation summary with transaction counts and amounts.
    
    Supports grouping by:
    - merchant: Summary per merchant
    - date: Summary per date
    - status: Summary per transaction status
    - all: Overall summary
    
    Query parameters:
    - merchant_id: Filter by merchant ID
    - start_date: Start date for filtering
    - end_date: End date for filtering
    - group_by: Dimension to group by (merchant, date, status, all)
    """
    try:
        # Validate group_by
        if group_by not in ["merchant", "date", "status", "all"]:
            raise HTTPException(status_code=400, detail="Invalid group_by value")

        service = ReconciliationService(db)
        return service.get_summary(
            merchant_id=merchant_id,
            start_date=start_date,
            end_date=end_date,
            group_by=group_by
        )

    except APIException as e:
        raise HTTPException(status_code=e.status_code, detail=str(e.message))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get(
    "/discrepancies",
    response_model=DiscrepancyResponse,
    responses={
        200: {"description": "List of transactions with discrepancies"},
    }
)
def get_discrepancies(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db)
):
    """
    Get transactions with discrepancies.
    
    Detects the following types of discrepancies:
    - processed_not_settled: Payment marked as processed but never settled
    - settled_after_failed: Payment settled but has a failed event
    - duplicate_initiated: Multiple payment_initiated events for same transaction
    
    Query parameters:
    - page: Page number (1-indexed)
    - limit: Items per page (1-100)
    """
    try:
        service = ReconciliationService(db)
        return service.get_discrepancies(page=page, limit=limit)

    except APIException as e:
        raise HTTPException(status_code=e.status_code, detail=str(e.message))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
