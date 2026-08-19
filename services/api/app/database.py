"""Database engine and session construction."""

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def build_engine(database_url: str) -> Engine:
    """Create an engine without hiding the configured database URL."""

    return create_engine(database_url, pool_pre_ping=True)


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create the canonical non-expiring session factory."""

    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
