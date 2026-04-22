"""Pydantic request schemas."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator


class EventPayloadRequest(BaseModel):
    """Request schema for posting payment events."""
    event_id: str = Field(..., description="Unique event identifier (UUID)")
    transaction_id: str = Field(..., description="Transaction identifier (UUID)")
    merchant_id: str = Field(..., min_length=1, max_length=100, description="Merchant identifier")
    merchant_name: str = Field(..., min_length=1, max_length=255, description="Merchant name")
    event_type: Literal[
        "payment_initiated", "payment_processed", "payment_failed", "settled"
    ] = Field(..., description="Type of payment event")
    amount: Decimal = Field(..., gt=0, description="Transaction amount (must be > 0)")
    currency: str = Field(..., min_length=3, max_length=3, description="Currency code (e.g., INR)")
    timestamp: datetime = Field(..., description="Event timestamp")

    @field_validator("event_id", "transaction_id", mode="before")
    @classmethod
    def validate_uuids(cls, v):
        """Validate that event_id and transaction_id are valid UUIDs."""
        try:
            UUID(str(v))
            return str(v)
        except (ValueError, TypeError):
            raise ValueError("Must be a valid UUID")

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v):
        """Validate currency is uppercase."""
        return v.upper()

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "event_id": "b768e3a7-9eb3-4603-b21c-a54cc95661bc",
                "transaction_id": "2f86e94c-239c-4302-9874-75f28e3474ee",
                "merchant_id": "merchant_1",
                "merchant_name": "QuickMart",
                "event_type": "payment_initiated",
                "amount": "9169.41",
                "currency": "INR",
                "timestamp": "2026-01-08T12:11:58.085567",
            }
        }
    )


