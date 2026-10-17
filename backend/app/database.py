from collections.abc import Generator

from fastapi import Request
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def sqlite_constraints(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")


class Base(DeclarativeBase):
    pass


def get_db(request: Request) -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        # GET order reads can expire commitments and therefore also require a lock.
        # Relay listings may close an expired relay, which also replans.
        writes = request.method != "GET" or request.url.path.startswith(("/api/orders", "/api/relays"))
        if writes:
            if engine.dialect.name == "sqlite":
                db.execute(text("BEGIN IMMEDIATE"))
            elif engine.dialect.name == "postgresql":
                db.execute(text("SELECT pg_advisory_xact_lock(731940)"))
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
