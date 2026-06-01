from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from bot.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    import bot.database.models

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        columns = await connection.execute(text("PRAGMA table_info(plans)"))
        plan_column_names = {row[1] for row in columns}
        if "price" not in plan_column_names:
            await connection.execute(text("ALTER TABLE plans ADD COLUMN price INTEGER NOT NULL DEFAULT 0"))

        order_columns = await connection.execute(text("PRAGMA table_info(orders)"))
        order_column_names = {row[1] for row in order_columns}
        if "config_text" not in order_column_names:
            await connection.execute(text("ALTER TABLE orders ADD COLUMN config_text TEXT"))
        if "approved_at" not in order_column_names:
            await connection.execute(text("ALTER TABLE orders ADD COLUMN approved_at DATETIME"))
