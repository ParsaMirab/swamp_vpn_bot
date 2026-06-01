from sqlalchemy import delete, select

from bot.database.base import async_session_factory
from bot.database.models import BankCard
from bot.services.plan_service import PlanService


class BankCardService:
    @staticmethod
    async def list_cards() -> list[BankCard]:
        async with async_session_factory() as session:
            result = await session.execute(select(BankCard).order_by(BankCard.id.asc()))
            return list(result.scalars().all())

    @staticmethod
    async def get_first_card() -> BankCard | None:
        async with async_session_factory() as session:
            result = await session.execute(select(BankCard).order_by(BankCard.id.asc()).limit(1))
            return result.scalar_one_or_none()

    @staticmethod
    async def create_card(card_number: str, owner_name: str) -> BankCard:
        normalized_card_number = BankCardService.normalize_card_number(card_number)
        normalized_owner_name = BankCardService.normalize_owner_name(owner_name)

        async with async_session_factory() as session:
            card = BankCard(card_number=normalized_card_number, owner_name=normalized_owner_name)
            session.add(card)
            await session.commit()
            await session.refresh(card)
            return card

    @staticmethod
    async def delete_card(card_id: int) -> bool:
        async with async_session_factory() as session:
            result = await session.execute(delete(BankCard).where(BankCard.id == card_id))
            await session.commit()
            return bool(result.rowcount)

    @staticmethod
    def normalize_card_number(card_number: str) -> str:
        normalized_card_number = PlanService.normalize_digits(card_number).replace(" ", "").replace("-", "")
        if not normalized_card_number.isdigit():
            raise ValueError("شماره کارت باید فقط عدد باشد.")
        if len(normalized_card_number) != 16:
            raise ValueError("شماره کارت باید 16 رقم باشد.")
        return normalized_card_number

    @staticmethod
    def normalize_owner_name(owner_name: str) -> str:
        normalized_owner_name = owner_name.strip()
        if not normalized_owner_name:
            raise ValueError("نام صاحب کارت را ارسال کنید.")
        if len(normalized_owner_name) > 255:
            raise ValueError("نام صاحب کارت نباید بیشتر از 255 کاراکتر باشد.")
        return normalized_owner_name

    @staticmethod
    def mask_card_number(card_number: str) -> str:
        return f"{card_number[:4]}********{card_number[-4:]}"
