from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, update

from bot.database.base import async_session_factory
from bot.database.models import RechargePackage, UserWallet, WalletTransaction

wallet_logger = logging.getLogger("wallet")


class WalletService:
    @staticmethod
    async def get_or_create_wallet(user_id: int) -> UserWallet:
        async with async_session_factory() as session:
            result = await session.execute(
                select(UserWallet).where(UserWallet.user_id == user_id)
            )
            wallet = result.scalar_one_or_none()
            if wallet is not None:
                return wallet

            wallet = UserWallet(
                user_id=user_id,
                balance=0,
            )
            session.add(wallet)
            await session.commit()
            return wallet

    @staticmethod
    async def get_balance(user_id: int) -> int:
        wallet = await WalletService.get_or_create_wallet(user_id)
        return wallet.balance

    @staticmethod
    async def create_credit_transaction(
        user_id: int,
        amount: int,
        description: str | None = None,
        receipt_file_id: str | None = None,
    ) -> WalletTransaction:
        async with async_session_factory() as session:
            transaction = WalletTransaction(
                user_id=user_id,
                transaction_type="credit",
                amount=amount,
                status="pending",
                description=description,
                receipt_file_id=receipt_file_id,
            )
            session.add(transaction)
            await session.commit()
            return transaction

    @staticmethod
    async def create_debit_transaction(
        user_id: int,
        amount: int,
        description: str | None = None,
    ) -> WalletTransaction:
        async with async_session_factory() as session:
            result = await session.execute(
                select(UserWallet).where(UserWallet.user_id == user_id)
            )
            wallet = result.scalar_one_or_none()
            if wallet is None:
                wallet = UserWallet(user_id=user_id, balance=0)
                session.add(wallet)
                await session.flush()

            wallet.balance -= amount
            transaction = WalletTransaction(
                user_id=user_id,
                transaction_type="debit",
                amount=amount,
                status="approved",
                description=description,
                approved_at=datetime.now(timezone.utc),
            )
            session.add(transaction)
            await session.commit()
            return transaction

    @staticmethod
    async def _get_wallet_for_update(session: Any, user_id: int) -> UserWallet:
        result = await session.execute(
            select(UserWallet).where(UserWallet.user_id == user_id)
        )
        wallet = result.scalar_one_or_none()
        if wallet is None:
            wallet = UserWallet(user_id=user_id, balance=0)
            session.add(wallet)
            await session.flush()
        return wallet

    @staticmethod
    async def approve_transaction(
        transaction_id: int,
        admin_id: int,
    ) -> WalletTransaction | None:
        async with async_session_factory() as session:
            result = await session.execute(
                select(WalletTransaction).where(WalletTransaction.id == transaction_id)
            )
            transaction = result.scalar_one_or_none()
            if transaction is None:
                return None
            if transaction.status != "pending":
                return None

            transaction.status = "approved"
            transaction.admin_id = admin_id
            transaction.approved_at = datetime.now(timezone.utc)
            await session.flush()

            if transaction.transaction_type == "credit":
                wallet = await WalletService._get_wallet_for_update(
                    session, transaction.user_id
                )
                wallet.balance += transaction.amount
                wallet_logger.info(
                    "WALLET_CREDIT user=%s amount=%d transaction_id=%d balance_after=%d",
                    transaction.user_id, transaction.amount, transaction.id, wallet.balance,
                )

            await session.commit()
            return transaction

    @staticmethod
    async def reject_transaction(
        transaction_id: int,
        admin_id: int,
    ) -> WalletTransaction | None:
        async with async_session_factory() as session:
            result = await session.execute(
                select(WalletTransaction).where(WalletTransaction.id == transaction_id)
            )
            transaction = result.scalar_one_or_none()
            if transaction is None:
                return None
            if transaction.status != "pending":
                return None

            transaction.status = "rejected"
            transaction.admin_id = admin_id
            await session.commit()
            return transaction

    @staticmethod
    async def get_transaction(transaction_id: int) -> WalletTransaction | None:
        async with async_session_factory() as session:
            result = await session.execute(
                select(WalletTransaction).where(
                    WalletTransaction.id == transaction_id
                )
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def list_user_transactions(
        user_id: int,
    ) -> list[WalletTransaction]:
        async with async_session_factory() as session:
            result = await session.execute(
                select(WalletTransaction)
                .where(WalletTransaction.user_id == user_id)
                .order_by(WalletTransaction.created_at.desc())
            )
            return list(result.scalars().all())

    @staticmethod
    async def list_pending_transactions() -> list[WalletTransaction]:
        async with async_session_factory() as session:
            result = await session.execute(
                select(WalletTransaction)
                .where(WalletTransaction.status == "pending")
                .order_by(WalletTransaction.created_at.asc())
            )
            return list(result.scalars().all())

    @staticmethod
    async def has_sufficient_balance(user_id: int, amount: int) -> bool:
        balance = await WalletService.get_balance(user_id)
        return balance >= amount

    @staticmethod
    async def deduct_balance(
        user_id: int,
        amount: int,
        description: str | None = None,
    ) -> WalletTransaction:
        async with async_session_factory() as session:
            result = await session.execute(
                select(UserWallet)
                .where(UserWallet.user_id == user_id)
                .with_for_update()
            )
            wallet = result.scalar_one_or_none()
            if wallet is None:
                wallet = UserWallet(user_id=user_id, balance=0)
                session.add(wallet)
                await session.flush()

            if wallet.balance < amount:
                raise ValueError("موجودی کیف پول کافی نیست.")

            wallet.balance -= amount
            transaction = WalletTransaction(
                user_id=user_id,
                transaction_type="debit",
                amount=amount,
                status="approved",
                description=description,
                approved_at=datetime.now(timezone.utc),
            )
            session.add(transaction)
            await session.commit()

            wallet_logger.info(
                "WALLET_DEBIT user=%s amount=%d balance_after=%d description=%s",
                user_id, amount, wallet.balance, description,
            )
            return transaction

    @staticmethod
    async def refund_balance(
        user_id: int,
        amount: int,
        description: str | None = None,
    ) -> WalletTransaction:
        async with async_session_factory() as session:
            result = await session.execute(
                select(UserWallet)
                .where(UserWallet.user_id == user_id)
                .with_for_update()
            )
            wallet = result.scalar_one_or_none()
            if wallet is None:
                wallet = UserWallet(user_id=user_id, balance=0)
                session.add(wallet)
                await session.flush()

            wallet.balance += amount
            transaction = WalletTransaction(
                user_id=user_id,
                transaction_type="credit",
                amount=amount,
                status="approved",
                description=description or "بازگشت وجه",
                approved_at=datetime.now(timezone.utc),
            )
            session.add(transaction)
            await session.commit()

            wallet_logger.info(
                "WALLET_REFUND user=%s amount=%d balance_after=%d description=%s",
                user_id, amount, wallet.balance, description,
            )
            return transaction

    @staticmethod
    async def recharge_success_text(transaction: WalletTransaction) -> str:
        return (
            f"✅ شارژ کیف پول شما تایید شد.\n\n"
            f"مبلغ: {transaction.amount:,} تومان\n"
            f"شماره پیگیری: {transaction.id}"
        )

    @staticmethod
    async def recharge_rejected_text(transaction: WalletTransaction) -> str:
        return (
            f"❌ درخواست شارژ کیف پول شما رد شد.\n\n"
            f"مبلغ: {transaction.amount:,} تومان\n"
            f"شماره پیگیری: {transaction.id}\n\n"
            "در صورت وجود مشکل با پشتیبانی تماس بگیرید."
        )

    @staticmethod
    def transaction_status_label(status: str) -> str:
        labels = {
            "pending": "در انتظار بررسی",
            "approved": "تایید شده",
            "rejected": "رد شده",
        }
        return labels.get(status, status)

    @staticmethod
    def transaction_type_label(transaction_type: str) -> str:
        labels = {
            "credit": "واریز",
            "debit": "برداشت",
        }
        return labels.get(transaction_type, transaction_type)

    @staticmethod
    async def admin_notification_text(transaction: WalletTransaction) -> str:
        return (
            "💰 درخواست شارژ کیف پول\n\n"
            "کاربر:\n"
            f"{transaction.user_id}\n\n"
            "مبلغ:\n"
            f"{transaction.amount:,} تومان\n\n"
            "شماره تراکنش:\n"
            f"{transaction.id}"
        )

    @staticmethod
    def admin_transaction_details_text(transaction: WalletTransaction) -> str:
        text = (
            f"تراکنش: {transaction.id}\n\n"
            "کاربر:\n"
            f"{transaction.user_id}\n\n"
            "نوع:\n"
            f"{WalletService.transaction_type_label(transaction.transaction_type)}\n\n"
            "مبلغ:\n"
            f"{transaction.amount:,} تومان\n\n"
            "وضعیت:\n"
            f"{WalletService.transaction_status_label(transaction.status)}\n\n"
            "تاریخ:\n"
            f"{transaction.created_at}\n\n"
        )
        if transaction.description:
            text += f"توضیحات:\n{transaction.description}\n\n"
        if transaction.approved_at:
            text += f"تاریخ تایید:\n{transaction.approved_at}\n"
        return text

    @staticmethod
    async def user_balance_text(user_id: int) -> str:
        wallet = await WalletService.get_or_create_wallet(user_id)
        return f"💰 موجودی کیف پول شما:\n\n{wallet.balance:,} تومان"

    @staticmethod
    async def create_package(title: str, amount: int) -> RechargePackage:
        async with async_session_factory() as session:
            package = RechargePackage(title=title, amount=amount)
            session.add(package)
            await session.commit()
            return package

    @staticmethod
    async def list_active_packages() -> list[RechargePackage]:
        async with async_session_factory() as session:
            result = await session.execute(
                select(RechargePackage)
                .where(RechargePackage.is_active == True)
                .order_by(RechargePackage.amount.asc())
            )
            return list(result.scalars().all())

    @staticmethod
    async def list_all_packages() -> list[RechargePackage]:
        async with async_session_factory() as session:
            result = await session.execute(
                select(RechargePackage).order_by(RechargePackage.amount.asc())
            )
            return list(result.scalars().all())

    @staticmethod
    async def get_package(package_id: int) -> RechargePackage | None:
        async with async_session_factory() as session:
            return await session.get(RechargePackage, package_id)

    @staticmethod
    async def delete_package(package_id: int) -> bool:
        async with async_session_factory() as session:
            package = await session.get(RechargePackage, package_id)
            if package is None:
                return False
            await session.delete(package)
            await session.commit()
            return True

    @staticmethod
    async def toggle_package(package_id: int) -> bool | None:
        async with async_session_factory() as session:
            package = await session.get(RechargePackage, package_id)
            if package is None:
                return None
            package.is_active = not package.is_active
            await session.commit()
            return package.is_active
