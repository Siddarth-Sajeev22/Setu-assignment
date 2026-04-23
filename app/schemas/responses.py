"""Pydantic response schemas."""
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from decimal import Decimal


class EventResponse(BaseModel):
    """Response schema for payment events."""
    id: int
    event_id: str
    transaction_id: str  # UUID string, not internal FK
    event_type: str
    timestamp: datetime
    created_at: datetime


class TransactionDetailResponse(BaseModel):
    """Response schema for transaction details with events."""
    id: int
    transaction_id: str
    merchant_id: str
    merchant_name: str
    amount: Decimal
    currency: str
    status: str
    created_at: datetime
    updated_at: datetime
    events: List[EventResponse] = []

    model_config = ConfigDict(from_attributes=True)


class PaginationInfo(BaseModel):
    """Pagination information."""
    total_count: int
    page: int
    limit: int
    total_pages: int


class TransactionListResponse(BaseModel):
    """Response schema for paginated transaction list."""
    data: List[TransactionDetailResponse]
    pagination: PaginationInfo


class SummaryStat(BaseModel):
    """Summary statistic for reconciliation."""
    dimension: str  # e.g., "merchant_1", "2026-01-08", "settled"
    dimension_type: str  # "merchant", "date", or "status"
    transaction_count: int
    total_amount: Decimal


class ReconciliationSummaryResponse(BaseModel):
    """Response schema for reconciliation summary."""
    summaries: List[SummaryStat]
    group_by: str


class DiscrepancyItem(BaseModel):
    """Single discrepancy item."""
    transaction_id: str
    merchant_id: str
    merchant_name: str
    amount: Decimal
    currency: str
    status: str
    discrepancy_type: str  # "processed_not_settled", "settled_after_failed", "duplicate_initiated"
    reason: str
    events: List[EventResponse]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DiscrepancyResponse(BaseModel):
    """Response schema for discrepancies."""
    data: List[DiscrepancyItem]
    pagination: PaginationInfo


class ErrorResponse(BaseModel):
    """Generic error response."""
    error: str
    detail: Optional[str] = None
    status_code: int
