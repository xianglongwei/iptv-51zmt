"""
Lumina-IPTV Database Configuration
SQLAlchemy async engine with SQLite
"""
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String, DateTime, Boolean
from datetime import datetime

# Database path
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "iptv_manager.db")
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

# Async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True
)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Base class
Base = declarative_base()


# ============== Models ==============

class ChannelPool(Base):
    """原始频道池"""
    __tablename__ = "channel_pool"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tvg_name = Column(String(255), nullable=True, index=True)
    tvg_logo = Column(String(512), nullable=True)
    group_title = Column(String(128), nullable=True, index=True)
    live_url = Column(String(512), nullable=False, unique=True, index=True)
    catchup_type = Column(String(32), nullable=True)
    catchup_source = Column(String(512), nullable=True)
    is_active = Column(Boolean, default=True)  # True = online
    last_check = Column(DateTime, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    source_tag = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def to_dict(self):
        return {
            "id": self.id,
            "tvg_name": self.tvg_name,
            "tvg_logo": self.tvg_logo,
            "group_title": self.group_title,
            "live_url": self.live_url,
            "catchup_type": self.catchup_type,
            "catchup_source": self.catchup_source,
            "is_active": self.is_active,
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "latency_ms": self.latency_ms,
            "source_tag": self.source_tag,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class SelectedChannel(Base):
    """发布列表 - 用户选中的频道"""
    __tablename__ = "selected_channels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pool_id = Column(Integer, nullable=False, index=True)
    custom_name = Column(String(255), nullable=True)
    sort_order = Column(Integer, default=0)
    catchup_enabled = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)

    def to_dict(self):
        return {
            "id": self.id,
            "pool_id": self.pool_id,
            "custom_name": self.custom_name,
            "sort_order": self.sort_order,
            "catchup_enabled": self.catchup_enabled,
        }


# ============== Database Functions ==============

async def get_db():
    """Dependency for FastAPI"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Initialize database tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        result = await conn.exec_driver_sql("PRAGMA table_info(channel_pool)")
        columns = {row[1] for row in result.fetchall()}
        if "latency_ms" not in columns:
            await conn.exec_driver_sql("ALTER TABLE channel_pool ADD COLUMN latency_ms INTEGER")
