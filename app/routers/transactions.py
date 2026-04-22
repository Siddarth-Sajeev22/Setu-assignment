"""API router for transaction queries."""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from datetime import datetime
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.responses import (
    TransactionListResponse, TransactionDetailResponse, EventResponse, PaginationInfo
)
from app.schemas.exceptions import APIException
from app.repositories.transaction_repository import TransactionRepository

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get(
    "",
    response_model=TransactionListResponse,
    responses={
        200: {"description": "List of transactions"},
        400: {"description": "Invalid filter parameters"},
    }
)
def list_transactions(
    merchant_id: Optional[str] = Query(None, description="Filter by merchant ID"),
    status: Optional[str] = Query(None, description="Filter by transaction status"),
    start_date: Optional[datetime] = Query(None, description="Start date for filtering"),
    end_date: Optional[datetime] = Query(None, description="End date for filtering"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    order: str = Query("desc", description="Sort order"),
    db: Session = Depends(get_db)
):
    """
    List all transactions with optional filtering, sorting, and pagination.
    
    Query parameters:
    - merchant_id: Filter by merchant ID
    - status: Filter by status (initiated, processed, failed, settled)
    - start_date: Filter transactions created after this date
    - end_date: Filter transactions created before this date
    - page: Page number (1-indexed)
    - limit: Items per page (1-100)
    - sort_by: Field to sort by (created_at, amount, merchant_id)
    - order: Sort order (asc, desc)
    """
    try:
        # Validate sort_by and order
        if sort_by not in ["created_at", "amount", "merchant_id"]:
            raise HTTPException(status_code=400, detail="Invalid sort_by value")
        if order not in ["asc", "desc"]:
            raise HTTPException(status_code=400, detail="Invalid order value")
        if status and status not in ["initiated", "processed", "failed", "settled"]:
            raise HTTPException(status_code=400, detail="Invalid status value")

        txn_repo = TransactionRepository(db)

        transactions, total_count = txn_repo.list_transactions(
            merchant_id=merchant_id,
            status=status,
            start_date=start_date,
            end_date=end_date,
            page=page,
            limit=limit,
            sort_by=sort_by,
            order=order
        )

        # merchant and events are eager-loaded — no extra queries per row
        transaction_details = []
        for txn in transactions:
            detail = TransactionDetailResponse(
                id=txn.id,
                transaction_id=txn.transaction_id,
                merchant_id=txn.merchant.merchant_id,
                merchant_name=txn.merchant.merchant_name,
                amount=txn.amount,
                currency=txn.currency,
                status=txn.status,
                created_at=txn.created_at,
                updated_at=txn.updated_at,
                events=[EventResponse.model_validate(e) for e in txn.events],
            )
            transaction_details.append(detail)

        total_pages = (total_count + limit - 1) // limit
        pagination = PaginationInfo(
            total_count=total_count,
            page=page,
            limit=limit,
            total_pages=total_pages
        )

        return TransactionListResponse(
            data=transaction_details,
            pagination=pagination
        )

    except APIException as e:
        raise HTTPException(status_code=e.status_code, detail=str(e.message))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get(
    "/{transaction_id}",
    response_model=TransactionDetailResponse,
    responses={
        200: {"description": "Transaction details"},
        404: {"description": "Transaction not found"},
    }
)
def get_transaction(
    transaction_id: str,
    db: Session = Depends(get_db)
):
    """
    Get details of a specific transaction including full event history.
    
    Returns:
    - Transaction details (amount, status, merchant info, etc.)
    - Complete event history ordered by timestamp
    """
    try:
        txn_repo = TransactionRepository(db)

        # merchant and events are eager-loaded in get_by_transaction_id
        transaction = txn_repo.get_by_transaction_id(transaction_id)
        if not transaction:
            raise HTTPException(status_code=404, detail=f"Transaction not found: {transaction_id}")

        return TransactionDetailResponse(
            id=transaction.id,
            transaction_id=transaction.transaction_id,
            merchant_id=transaction.merchant.merchant_id,
            merchant_name=transaction.merchant.merchant_name,
            amount=transaction.amount,
            currency=transaction.currency,
            status=transaction.status,
            created_at=transaction.created_at,
            updated_at=transaction.updated_at,
            events=[EventResponse.model_validate(e) for e in transaction.events],
        )

    except APIException as e:
        raise HTTPException(status_code=e.status_code, detail=str(e.message))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
