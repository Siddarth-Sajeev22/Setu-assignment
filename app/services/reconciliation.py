"""Reconciliation service for summary and discrepancy queries."""
from typing import List, Optional
from datetime import datetime
from decimal import Decimal
from sqlalchemy.orm import Session
from app.schemas.responses import (
    SummaryStat, ReconciliationSummaryResponse, DiscrepancyItem,
    DiscrepancyResponse, PaginationInfo, EventResponse
)
from app.repositories.transaction_repository import TransactionRepository


class ReconciliationService:
    """Service for reconciliation queries and discrepancy detection."""

    def __init__(self, db: Session):
        self.db = db
        self.transaction_repo = TransactionRepository(db)

    def get_summary(
        self,
        merchant_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        group_by: str = "merchant"
    ) -> ReconciliationSummaryResponse:
        """
        Get reconciliation summary grouped by merchant, date, or status.
        All aggregation done in SQL.
        """
        results = self.transaction_repo.get_reconciliation_summary(
            merchant_id=merchant_id,
            start_date=start_date,
            end_date=end_date,
            group_by=group_by
        )

        summaries = []
        for row in results:
            if group_by == "all":
                # Row format: (transaction_count, total_amount)
                summary = SummaryStat(
                    dimension="all",
                    dimension_type="all",
                    transaction_count=row[0] or 0,
                    total_amount=Decimal(str(row[1] or 0)),
                )
            else:
                # Row format: (dimension, transaction_count, total_amount)
                summary = SummaryStat(
                    dimension=str(row[0]),
                    dimension_type=group_by,
                    transaction_count=row[1] or 0,
                    total_amount=Decimal(str(row[2] or 0)),
                )
            summaries.append(summary)

        return ReconciliationSummaryResponse(
            summaries=summaries,
            group_by=group_by
        )

    def get_discrepancies(
        self,
        page: int = 1,
        limit: int = 10
    ) -> DiscrepancyResponse:
        """
        Get transactions with discrepancies.
        Uses SQL subqueries to detect: processed-not-settled, settled-after-failed, duplicates.
        """
        transactions, total_count = self.transaction_repo.get_discrepancies(page, limit)

        # merchant and events are eager-loaded — no extra queries per row
        discrepancy_items = []
        for transaction in transactions:
            discrepancy_type = self._derive_discrepancy_type(transaction)
            reason = self._get_discrepancy_reason(transaction, discrepancy_type)
            item = DiscrepancyItem(
                transaction_id=transaction.transaction_id,
                merchant_id=transaction.merchant.merchant_id,
                merchant_name=transaction.merchant.merchant_name,
                amount=transaction.amount,
                currency=transaction.currency,
                status=transaction.status,
                discrepancy_type=discrepancy_type,
                reason=reason,
                events=[EventResponse.model_validate({
                    "id": e.id,
                    "event_id": e.event_id,
                    "transaction_id": transaction.transaction_id,
                    "event_type": e.event_type,
                    "timestamp": e.timestamp,
                    "created_at": e.created_at,
                }) for e in transaction.events],
                created_at=transaction.created_at,
            )
            discrepancy_items.append(item)

        # Calculate pagination
        total_pages = (total_count + limit - 1) // limit

        pagination = PaginationInfo(
            total_count=total_count,
            page=page,
            limit=limit,
            total_pages=total_pages
        )

        return DiscrepancyResponse(
            data=discrepancy_items,
            pagination=pagination
        )

    def _derive_discrepancy_type(self, transaction) -> str:
        """
        Derive discrepancy type from already-loaded transaction state.
        Mirrors the priority order of the SQL subqueries in get_discrepancies().
        """
        if transaction.status == "processed":
            return "processed_not_settled"
        if transaction.status == "settled":
            return "settled_after_failed"
        return "duplicate_initiated"

    def _get_discrepancy_reason(self, transaction, discrepancy_type: str) -> str:
        """Generate human-readable reason for discrepancy."""
        if discrepancy_type == "processed_not_settled":
            return (
                f"Transaction is in 'processed' status but has not been settled. "
                f"Amount: {transaction.amount} {transaction.currency}"
            )
        elif discrepancy_type == "settled_after_failed":
            return (
                f"Transaction is marked as 'settled' but has a 'payment_failed' event. "
                f"This indicates conflicting state transitions."
            )
        elif discrepancy_type == "duplicate_initiated":
            # Count from the already eager-loaded events — no extra query
            initiated_count = sum(
                1 for e in transaction.events if e.event_type == "payment_initiated"
            )
            return (
                f"Transaction has {initiated_count} 'payment_initiated' events. "
                f"Expected exactly one initiation event per transaction."
            )
        return "Unknown discrepancy type"
