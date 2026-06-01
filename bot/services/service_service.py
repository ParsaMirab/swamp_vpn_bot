from sqlalchemy import select
from sqlalchemy.orm import selectinload

from bot.database.base import async_session_factory
from bot.database.models import Service


class ServiceService:
    @staticmethod
    async def list_services() -> list[Service]:
        async with async_session_factory() as session:
            result = await session.execute(select(Service).order_by(Service.id.asc()))
            return list(result.scalars().all())

    @staticmethod
    async def get_service(service_id: int) -> Service | None:
        async with async_session_factory() as session:
            return await session.get(Service, service_id)

    @staticmethod
    async def create_service(name: str) -> Service:
        normalized_name = ServiceService.normalize_name(name)
        service = Service(name=normalized_name)

        async with async_session_factory() as session:
            session.add(service)
            await session.commit()
            await session.refresh(service)
            return service

    @staticmethod
    async def delete_service(service_id: int) -> bool:
        async with async_session_factory() as session:
            result = await session.execute(
                select(Service)
                .options(selectinload(Service.plans))
                .where(Service.id == service_id)
            )
            service = result.scalar_one_or_none()
            if service is None:
                return False

            await session.delete(service)
            await session.commit()
            return True

    @staticmethod
    def normalize_name(name: str) -> str:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("نام سرویس را ارسال کنید.")
        if len(normalized_name) > 255:
            raise ValueError("نام سرویس نباید بیشتر از ۲۵۵ کاراکتر باشد.")
        return normalized_name
