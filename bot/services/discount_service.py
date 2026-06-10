from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from bot.database.base import async_session_factory
from bot.database.models import DiscountCode, DiscountUsage
from bot.services.plan_service import PlanService


class DiscountCodeService:
    invalid_message = "❌ کد تخفیف نامعتبر است."

    @staticmethod
    async def list_discounts() -> list[DiscountCode]:
        async with async_session_factory() as session:
            result = await session.execute(
                select(DiscountCode)
                .options(selectinload(DiscountCode.usages))
                .order_by(DiscountCode.id.asc())
            )
            return list(result.scalars().all())

    @staticmethod
    async def create_discount(
        code: str,
        usage_limit: int,
        per_user_usage_limit: int,
        discount_amount: int,
        expires_at: datetime | None = None,
    ) -> DiscountCode:
        normalized_code = DiscountCodeService.normalize_code(code)
        normalized_usage_limit = DiscountCodeService.normalize_positive_int(
            usage_limit,
            "سقف استفاده باید عدد مثبت باشد.",
        )
        normalized_per_user_usage_limit = DiscountCodeService.normalize_positive_int(
            per_user_usage_limit,
            "سقف استفاده برای هر کاربر باید عدد مثبت باشد.",
        )
        normalized_discount_amount = DiscountCodeService.normalize_positive_int(
            discount_amount,
            "مبلغ تخفیف باید عدد مثبت باشد.",
        )

        async with async_session_factory() as session:
            discount = DiscountCode(
                code=normalized_code,
                usage_limit=normalized_usage_limit,
                per_user_usage_limit=normalized_per_user_usage_limit,
                discount_amount=normalized_discount_amount,
                used_count=0,
                expires_at=expires_at,
            )
            session.add(discount)
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise ValueError("این کد تخفیف قبلاً ثبت شده است.") from exc
            await session.refresh(discount)
            return discount

    @staticmethod
    async def delete_discount(discount_id: int) -> bool:
        async with async_session_factory() as session:
            result = await session.execute(delete(DiscountCode).where(DiscountCode.id == discount_id))
            await session.commit()
            return bool(result.rowcount)

    @staticmethod
    async def apply_discount(code: str, user_id: int, plan_price: int) -> tuple[DiscountCode, int]:
        normalized_code = DiscountCodeService.normalize_code(code)

        async with async_session_factory() as session:
            result = await session.execute(
                select(DiscountCode)
                .options(selectinload(DiscountCode.usages))
                .where(DiscountCode.code == normalized_code)
            )
            discount = result.scalar_one_or_none()
            if discount is None:
                raise ValueError(DiscountCodeService.invalid_message)

            if discount.expires_at is not None:
                expires = discount.expires_at if discount.expires_at.tzinfo is not None else discount.expires_at.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) > expires:
                    raise ValueError(DiscountCodeService.invalid_message)

            if discount.used_count >= discount.usage_limit:
                raise ValueError(DiscountCodeService.invalid_message)

            per_user_count = await session.scalar(
                select(func.count())
                .select_from(DiscountUsage)
                .where(
                    DiscountUsage.discount_id == discount.id,
                    DiscountUsage.user_id == user_id,
                )
            )
            if per_user_count >= discount.per_user_usage_limit:
                raise ValueError(DiscountCodeService.invalid_message)

            final_price = max(plan_price - discount.discount_amount, 0)
            discount.used_count += 1
            session.add(DiscountUsage(discount_id=discount.id, user_id=user_id))
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise ValueError(DiscountCodeService.invalid_message) from exc
            await session.refresh(discount)
            return discount, final_price

    @staticmethod
    def normalize_code(code: str) -> str:
        normalized_code = code.strip().upper()
        if not normalized_code:
            raise ValueError("کد تخفیف را ارسال کنید.")
        if len(normalized_code) > 64:
            raise ValueError("کد تخفیف نباید بیشتر از 64 کاراکتر باشد.")
        return normalized_code

    @staticmethod
    def parse_positive_int(value: str, error_message: str) -> int:
        normalized_value = PlanService.normalize_digits(value).strip()
        if not normalized_value.isdigit():
            raise ValueError(error_message)
        return DiscountCodeService.normalize_positive_int(int(normalized_value), error_message)

    @staticmethod
    def normalize_positive_int(value: int, error_message: str) -> int:
        if value <= 0:
            raise ValueError(error_message)
        return value
