from sqlalchemy import Column, Integer, String, BigInteger, Float, DateTime, create_engine

# [2024-09-22] Коммит: обновление логики бэкенда и синхронизация с frontend
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime

DATABASE_URL = "sqlite+aiosqlite:///./clicker.db"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)
    username = Column(String(255), nullable=True)
    click_count = Column(Integer, default=0)
    purchases = Column(String, default="")
    boost_multiplier = Column(Float, default=1.0)
    boost_expires_at = Column(DateTime, nullable=True)


class GlobalStats(Base):
    __tablename__ = "global_stats"

    id = Column(Integer, primary_key=True, index=True)
    total_clicks = Column(BigInteger, default=0)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
