from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

engine = create_engine(settings.sqlalchemy_database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    except Exception:
        # Roll back on *any* unexpected exit, not just SQLAlchemyError. A
        # business-validation error raised mid-handler (ValueError, HTTPException
        # after a partial flush, etc.) would previously close the session
        # without rolling back, leaving any earlier autoflushed write
        # committed-but-orphaned. The bare `raise` preserves propagation.
        db.rollback()
        raise
    finally:
        db.close()
