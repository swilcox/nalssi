"""
API dependencies for dependency injection.
"""

from app.database import SessionLocal


def get_db():
    """
    Get database session.

    Yields:
        Database session

    Usage:
        @app.get("/items")
        def read_items(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
