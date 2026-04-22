"""Base repository class with common utilities."""
from sqlalchemy.orm import Session
from app.schemas.exceptions import DatabaseError


class BaseRepository:
    """Base repository with common database operations."""

    def __init__(self, db: Session):
        self.db = db

    def commit(self):
        """Commit transaction."""
        try:
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Failed to commit transaction: {str(e)}")

    def rollback(self):
        """Rollback transaction."""
        self.db.rollback()

    def flush(self):
        """Flush transaction."""
        try:
            self.db.flush()
        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Failed to flush transaction: {str(e)}")
