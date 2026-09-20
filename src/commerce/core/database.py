from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from commerce.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    connect_args = (
        {"check_same_thread": False}
        if settings.database_url.startswith("sqlite")
        else {"connect_timeout": 2}
    )
    return create_engine(
        settings.database_url,
        echo=settings.app_debug,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


def create_db_and_tables() -> None:
    from commerce.domain import models  # noqa: F401

    SQLModel.metadata.create_all(get_engine())


def check_database() -> bool:
    with Session(get_engine()) as session:
        session.execute(text("SELECT 1"))
    return True


def get_session() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session
