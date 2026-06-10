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

        discount_code_columns = await connection.execute(text("PRAGMA table_info(discount_codes)"))
        discount_code_column_names = {row[1] for row in discount_code_columns}
        if "per_user_usage_limit" not in discount_code_column_names:
            await connection.execute(text(
                "ALTER TABLE discount_codes ADD COLUMN per_user_usage_limit INTEGER NOT NULL DEFAULT 1"
            ))
        if "expires_at" not in discount_code_column_names:
            await connection.execute(text(
                "ALTER TABLE discount_codes ADD COLUMN expires_at DATETIME"
            ))

        if "sub_link" not in order_column_names:
            await connection.execute(text(
                "ALTER TABLE orders ADD COLUMN sub_link TEXT"
            ))

        discount_usage_columns = await connection.execute(text("PRAGMA table_info(discount_usages)"))
        discount_usage_column_names = {row[1] for row in discount_usage_columns}
        if "plan_id" in discount_usage_column_names:
            await connection.execute(text("PRAGMA foreign_keys=OFF"))
            await connection.execute(text("DROP INDEX IF EXISTS ix_discount_usages_discount_id"))
            await connection.execute(text("DROP INDEX IF EXISTS ix_discount_usages_user_id"))
            await connection.execute(text("DROP INDEX IF EXISTS ix_discount_usages_plan_id"))
            await connection.execute(text("""
                CREATE TABLE IF NOT EXISTS discount_usages_new (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    discount_id INTEGER NOT NULL REFERENCES discount_codes(id) ON DELETE CASCADE,
                    user_id BIGINT NOT NULL,
                    used_at DATETIME NOT NULL DEFAULT (datetime('now'))
                )
            """))
            await connection.execute(text("CREATE INDEX ix_discount_usages_discount_id ON discount_usages_new(discount_id)"))
            await connection.execute(text("CREATE INDEX ix_discount_usages_user_id ON discount_usages_new(user_id)"))
            await connection.execute(text("""
                INSERT INTO discount_usages_new (id, discount_id, user_id, used_at)
                SELECT id, discount_id, user_id, used_at FROM discount_usages
            """))
            await connection.execute(text("DROP TABLE discount_usages"))
            await connection.execute(text("ALTER TABLE discount_usages_new RENAME TO discount_usages"))
            await connection.execute(text("PRAGMA foreign_keys=ON"))

        result = await connection.execute(text("SELECT COUNT(*) FROM settings WHERE key = 'sales_open'"))
        if result.scalar_one() == 0:
            await connection.execute(text("INSERT INTO settings (key, value) VALUES ('sales_open', 'true')"))

        user_count = await connection.execute(text("SELECT COUNT(*) FROM users"))
        if user_count.scalar_one() == 0:
            await connection.execute(text("""
                INSERT OR IGNORE INTO users (id, first_seen, last_active)
                SELECT DISTINCT user_id, datetime('now'), datetime('now')
                FROM orders
            """))
