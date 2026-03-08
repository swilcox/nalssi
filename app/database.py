"""
Database configuration and session management.
"""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

# Create database engine
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False}
    if "sqlite" in settings.DATABASE_URL
    else {},
)

# Configure SQLite for immediate disk persistence
if "sqlite" in settings.DATABASE_URL:

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        """
        Set SQLite PRAGMAs for data integrity and immediate disk writes.

        - synchronous=FULL: Full fsync on every commit (safest, slower)
        - journal_mode=DELETE: Traditional rollback journal (simpler than WAL)
        - foreign_keys=ON: Enforce foreign key constraints

        Note: These settings prioritize data safety over performance.
        For production with high write volume, consider PostgreSQL.
        """
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA synchronous = FULL")
        cursor.execute("PRAGMA journal_mode = DELETE")
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()


# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base class for declarative models
Base = declarative_base()


def get_db():
    """
    Dependency function to get database session.
    Used in FastAPI endpoints.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
