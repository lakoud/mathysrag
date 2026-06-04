"""Database session management."""

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from rems.config import settings
from rems.models.database import Base

engine = create_engine(settings.database_url, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Create all database tables."""
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Get a database session as a context manager."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
