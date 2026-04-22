"""Transaction repository for database operations on transactions."""
from typing import Optional, List, Tuple
from datetime import datetime
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy import func, and_, or_
from sqlalchemy.exc import IntegrityError
from app.models import Transaction, PaymentEvent, Merchant
from app.repositories.base import BaseRepository
from app.schemas.exceptions import DatabaseError


class TransactionRepository(BaseRepository):
    """Repository for Transaction model operations."""

    def __init__(self, db: Session):
        super().__init__(db)

    def get_by_transaction_id(self, transaction_id: str) -> Optional[Transaction]:
        """Get transaction by transaction_id, with merchant and events eager-loaded."""
        return (
            self.db.query(Transaction)
            .options(joinedload(Transaction.merchant), selectinload(Transaction.events))
            .filter(Transaction.transaction_id == transaction_id)
            .first()
        )

    def get_by_id(self, pk_id: int) -> Optional[Transaction]:
        """Get transaction by primary key."""
        return self.db.query(Transaction).filter(
            Transaction.id == pk_id
        ).first()

    def create_transaction(
        self,
        transaction_id: str,
        merchant_id: int,
        amount,
        currency: str,
        status: str
    ) -> Transaction:
        """Create and insert new transaction."""
        try:
            transaction = Transaction(
                transaction_id=transaction_id,
                merchant_id=merchant_id,
                amount=amount,
                currency=currency,
                status=status
            )
            self.db.add(transaction)
            self.flush()
            return transaction
        except IntegrityError:
            self.rollback()
            raise DatabaseError(f"Transaction with this ID already exists: {transaction_id}")

    def update_transaction_status(self, transaction_id: int, status: str) -> Transaction:
        """Update transaction status by primary key."""
        try:
            transaction = self.db.query(Transaction).filter(
                Transaction.id == transaction_id
            ).first()
            if not transaction:
                raise DatabaseError(f"Transaction not found: {transaction_id}")
            transaction.status = status
            self.flush()
            return transaction
        except Exception as e:
            self.rollback()
            raise DatabaseError(f"Failed to update transaction status: {str(e)}")

    def list_transactions(
        self,
        merchant_id: Optional[str] = None,
        status: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        page: int = 1,
        limit: int = 10,
        sort_by: str = "created_at",
        order: str = "desc"
    ) -> Tuple[List[Transaction], int]:
        """
        List transactions with filtering, pagination, and sorting.
        Returns: (transactions, total_count)
        """
        query = self.db.query(Transaction).options(
            joinedload(Transaction.merchant),
            selectinload(Transaction.events),
        )

        # Apply filters
        if merchant_id:
            # Filter by merchant_id from Merchant table
            query = query.join(Merchant).filter(Merchant.merchant_id == merchant_id)

        if status:
            query = query.filter(Transaction.status == status)

        if start_date:
            query = query.filter(Transaction.created_at >= start_date)

        if end_date:
            query = query.filter(Transaction.created_at <= end_date)

        # Get total count before pagination
        total_count = query.count()

        # Apply sorting
        sort_column = {
            "created_at": Transaction.created_at,
            "amount": Transaction.amount,
            "merchant_id": Transaction.merchant_id
        }.get(sort_by, Transaction.created_at)

        if order == "asc":
            query = query.order_by(sort_column.asc())
        else:
            query = query.order_by(sort_column.desc())

        # Apply pagination
        offset = (page - 1) * limit
        transactions = query.offset(offset).limit(limit).all()

        return transactions, total_count

    def get_reconciliation_summary(
        self,
        merchant_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        group_by: str = "merchant"
    ) -> list:
        """
        Get reconciliation summary with aggregations.
        Groups by merchant, date, or status and counts transactions.
        All operations in SQL.
        """
        filters = []
        if merchant_id:
            filters.append(Merchant.merchant_id == merchant_id)
        if start_date:
            filters.append(Transaction.created_at >= start_date)
        if end_date:
            filters.append(Transaction.created_at <= end_date)

        if group_by == "merchant":
            q = self.db.query(
                Merchant.merchant_id.label("dimension"),
                func.count(Transaction.id).label("transaction_count"),
                func.sum(Transaction.amount).label("total_amount"),
            ).join(Transaction, Transaction.merchant_id == Merchant.id)
            if filters:
                q = q.filter(and_(*filters))
            return q.group_by(Merchant.merchant_id).all()

        elif group_by == "date":
            q = self.db.query(
                func.date(Transaction.created_at).label("dimension"),
                func.count(Transaction.id).label("transaction_count"),
                func.sum(Transaction.amount).label("total_amount"),
            ).join(Merchant, Transaction.merchant_id == Merchant.id)
            if filters:
                q = q.filter(and_(*filters))
            return q.group_by(func.date(Transaction.created_at)).all()

        elif group_by == "status":
            q = self.db.query(
                Transaction.status.label("dimension"),
                func.count(Transaction.id).label("transaction_count"),
                func.sum(Transaction.amount).label("total_amount"),
            ).join(Merchant, Transaction.merchant_id == Merchant.id)
            if filters:
                q = q.filter(and_(*filters))
            return q.group_by(Transaction.status).all()

        else:  # "all"
            q = self.db.query(
                func.count(Transaction.id).label("transaction_count"),
                func.sum(Transaction.amount).label("total_amount"),
            ).join(Merchant, Transaction.merchant_id == Merchant.id)
            if filters:
                q = q.filter(and_(*filters))
            return q.all()

    def get_discrepancies(
        self,
        page: int = 1,
        limit: int = 10
    ) -> Tuple[List[Transaction], int]:
        """
        Find transactions with discrepancies using SQL subqueries.

        Discrepancy types:
        - processed_not_settled: status = 'processed' but no 'settled' event
        - settled_after_failed: status = 'settled' but 'payment_failed' event exists
        - duplicate_initiated: multiple 'payment_initiated' events
        """
        # Correlated subquery: processed but no settled event
        processed_not_settled = self.db.query(Transaction.id).filter(
            Transaction.status == "processed",
            ~self.db.query(PaymentEvent.id).filter(
                PaymentEvent.transaction_id == Transaction.id,
                PaymentEvent.event_type == "settled"
            ).exists()
        )

        # Correlated subquery: settled but a failed event also exists
        settled_after_failed = self.db.query(Transaction.id).filter(
            Transaction.status == "settled",
            self.db.query(PaymentEvent.id).filter(
                PaymentEvent.transaction_id == Transaction.id,
                PaymentEvent.event_type == "payment_failed"
            ).exists()
        )

        # GROUP BY / HAVING: transactions with more than one payment_initiated event
        duplicate_initiated = (
            self.db.query(PaymentEvent.transaction_id)
            .filter(PaymentEvent.event_type == "payment_initiated")
            .group_by(PaymentEvent.transaction_id)
            .having(func.count(PaymentEvent.id) > 1)
        )

        discrepancy_query = self.db.query(Transaction).options(
            joinedload(Transaction.merchant),
            selectinload(Transaction.events),
        ).filter(
            or_(
                Transaction.id.in_(processed_not_settled),
                Transaction.id.in_(settled_after_failed),
                Transaction.id.in_(duplicate_initiated),
            )
        )

        total_count = discrepancy_query.count()
        offset = (page - 1) * limit
        transactions = (
            discrepancy_query
            .order_by(Transaction.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        return transactions, total_count

