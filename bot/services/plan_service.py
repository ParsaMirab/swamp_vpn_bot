from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload

from bot.database.base import async_session_factory
from bot.database.models import Plan, Service


class PlanService:
    @staticmethod
    async def list_plans(service_id: int) -> list[Plan]:
        async with async_session_factory() as session:
            result = await session.execute(
                select(Plan)
                .where(Plan.service_id == service_id)
                .order_by(Plan.id.asc())
            )
            return list(result.scalars().all())

    @staticmethod
    async def count_plans(service_id: int) -> int:
        async with async_session_factory() as session:
            result = await session.execute(
                select(func.count(Plan.id)).where(Plan.service_id == service_id)
            )
            return int(result.scalar_one())

    @staticmethod
    async def get_plan(plan_id: int, service_id: int | None = None) -> Plan | None:
        conditions = [Plan.id == plan_id]
        if service_id is not None:
            conditions.append(Plan.service_id == service_id)

        async with async_session_factory() as session:
            result = await session.execute(
                select(Plan)
                .options(selectinload(Plan.service))
                .where(*conditions)
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def create_plan(service_id: int, name: str, price: int) -> Plan:
        normalized_name = PlanService.normalize_name(name)
        normalized_price = PlanService.normalize_price(price)

        async with async_session_factory() as session:
            service = await session.get(Service, service_id)
            if service is None:
                raise ValueError("سرویس انتخاب‌شده پیدا نشد.")

            plan = Plan(service_id=service_id, name=normalized_name, price=normalized_price)
            session.add(plan)
            await session.commit()
            await session.refresh(plan)
            return plan

    @staticmethod
    async def delete_plan(plan_id: int, service_id: int | None = None) -> bool:
        conditions = [Plan.id == plan_id]
        if service_id is not None:
            conditions.append(Plan.service_id == service_id)

        async with async_session_factory() as session:
            result = await session.execute(delete(Plan).where(*conditions))
            await session.commit()
            return bool(result.rowcount)

    @staticmethod
    def normalize_name(name: str) -> str:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("نام پلن را ارسال کنید.")
        if len(normalized_name) > 255:
            raise ValueError("نام پلن نباید بیشتر از 255 کاراکتر باشد.")
        return normalized_name

    @staticmethod
    def normalize_price(price: int) -> int:
        if price <= 0:
            raise ValueError("قیمت پلن باید عدد مثبت باشد.")
        return price

    @staticmethod
    def parse_price(price_text: str) -> int:
        normalized_text = PlanService.normalize_digits(price_text).strip()
        if not normalized_text.isdigit():
            raise ValueError("قیمت را فقط به صورت عددی ارسال کنید.")
        return PlanService.normalize_price(int(normalized_text))

    @staticmethod
    def normalize_digits(value: str) -> str:
        translation = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
        return value.translate(translation)
