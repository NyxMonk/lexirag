from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

engine = create_engine(get_settings().sqlalchemy_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_database() -> dict[str, object]:
    """Return connectivity and pgvector status without raising."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            version = conn.execute(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            ).scalar()
        return {"status": "ok", "pgvector": version is not None, "pgvector_version": version}
    except Exception as exc:  # noqa: BLE001 - surfaced as health state
        return {"status": "unavailable", "pgvector": False, "error": exc.__class__.__name__}
