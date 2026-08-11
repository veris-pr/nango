from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from nango.server.models import Base

engine = None
SessionLocal = None


def init_db(database_url: str) -> None:
    global engine, SessionLocal

    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def create_tables() -> None:
    if engine:
        Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    if not SessionLocal:
        raise RuntimeError("Database not initialized. Call init_db() first.")

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()