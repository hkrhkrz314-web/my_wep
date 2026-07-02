"""
===================================================================
Project: Wolf Host - لوحة استضافة البوتات
Author: @BLACK_ZERO2
Channel: https://t.me/ROXScripts2
Year: 2026
License: MIT
===================================================================
"""

from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import settings


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


class BotType(str, Enum):
    """Supported bot runtime types."""
    PYTHON = "python"
    PHP = "php"


class BotStatus(str, Enum):
    """Possible states for a managed bot process."""
    STOPPED = "stopped"
    RUNNING = "running"
    CRASHED = "crashed"
    INSTALLING = "installing"


class Bot(Base):
    """ORM model representing a single managed bot instance."""

    __tablename__ = "bots"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    name: str = Column(String(255), unique=True, nullable=False, index=True)
    bot_type: str = Column(String(10), nullable=False)
    script_file: str = Column(String(255), nullable=False)
    directory: str = Column(String(512), nullable=False)
    pid: int | None = Column(Integer, nullable=True)
    status: str = Column(String(20), default=BotStatus.STOPPED.value)
    auto_restart: bool = Column(Boolean, default=True)
    restart_count: int = Column(Integer, default=0)
    created_at: datetime = Column(DateTime, default=datetime.utcnow)
    updated_at: datetime = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    last_started_at: datetime | None = Column(DateTime, nullable=True)
    last_stopped_at: datetime | None = Column(DateTime, nullable=True)
    error_message: str | None = Column(Text, nullable=True)


engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def init_db() -> None:
    """Create all database tables if they do not exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """Yield an async database session for dependency injection."""
    async with async_session() as session:
        yield session
