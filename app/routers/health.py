"""API router for health checks."""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health", responses={200: {"description": "Service is healthy"}})
def health_check(db: Session = Depends(get_db)):
    """
    Health check endpoint for deployment monitoring.
    Verifies database connectivity.
    """
    try:
        # Test database connection
        db.execute(text("SELECT 1"))
        return {
            "status": "healthy",
            "message": "Payment events service is running"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "message": f"Database connection failed: {str(e)}"
        }
