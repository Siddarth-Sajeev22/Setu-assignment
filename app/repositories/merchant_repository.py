"""Merchant repository for database operations on merchants."""
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.models import Merchant
from app.repositories.base import BaseRepository
from app.schemas.exceptions import DatabaseError


class MerchantRepository(BaseRepository):
    """Repository for Merchant model operations."""

    def __init__(self, db: Session):
        super().__init__(db)

    def get_or_create_merchant(self, merchant_id: str, merchant_name: str) -> Merchant:
        """Get existing merchant or create new one. Idempotent operation."""
        # Try to get existing merchant
        merchant = self.db.query(Merchant).filter(
            Merchant.merchant_id == merchant_id
        ).first()

        if merchant:
            return merchant

        # Create new merchant
        try:
            merchant = Merchant(
                merchant_id=merchant_id,
                merchant_name=merchant_name
            )
            self.db.add(merchant)
            self.flush()
            return merchant
        except IntegrityError:
            # Race condition: merchant was created by another request
            self.rollback()
            merchant = self.db.query(Merchant).filter(
                Merchant.merchant_id == merchant_id
            ).first()
            if merchant:
                return merchant
            raise DatabaseError(f"Failed to create or retrieve merchant: {merchant_id}")

