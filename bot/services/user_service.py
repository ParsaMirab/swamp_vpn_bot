from datetime import datetime, timezone

from sqlalchemy import select, update

from bot.database.base import async_session_factory
from bot.database.models import User


class UserService:
    @staticmethod
    async def register_user(user_id: int, username: str | None = None) -> User:
        async with async_session_factory() as session:
            existing = await session.get(User, user_id)
            if existing is not None:
                existing.last_active = datetime.now(timezone.utc)
                if username is not None:
                    existing.username = username
                await session.commit()
                return existing

            user = User(
                id=user_id,
                username=username,
                first_seen=datetime.now(timezone.utc),
                last_active=datetime.now(timezone.utc),
            )
            session.add(user)
            await session.commit()
            return user

    @staticmethod
    async def list_all_user_ids() -> list[int]:
        async with async_session_factory() as session:
            result = await session.execute(select(User.id).order_by(User.id.asc()))
            return [row[0] for row in result]

    @staticmethod
    async def count_users() -> int:
        async with async_session_factory() as session:
            result = await session.execute(select(User.id))
            return len(result.all())
