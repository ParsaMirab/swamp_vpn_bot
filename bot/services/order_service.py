from __future__ import annotations

from datetime import datetime, timezone
from html import escape

from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from bot.database.base import async_session_factory
from bot.database.models import Order


class OrderService:
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    page_size = 8

    @staticmethod
    async def create_order(
        user_id: int,
        service_id: int,
        plan_id: int,
        original_price: int,
        final_price: int,
        discount_id: int | None = None,
        receipt_file_id: str | None = None,
    ) -> Order:
        async with async_session_factory() as session:
            order = Order(
                user_id=user_id,
                service_id=service_id,
                plan_id=plan_id,
                discount_id=discount_id,
                original_price=original_price,
                final_price=final_price,
                receipt_file_id=receipt_file_id,
                status=OrderService.pending,
            )
            session.add(order)
            await session.commit()
            stored_order = await OrderService.get_order(order.id)
            if stored_order is None:
                raise RuntimeError("Order was created but could not be loaded.")
            return stored_order

    @staticmethod
    async def attach_receipt(order_id: int, user_id: int, receipt_file_id: str) -> Order | None:
        async with async_session_factory() as session:
            order = await session.get(Order, order_id)
            if order is None or order.user_id != user_id:
                return None

            order.receipt_file_id = receipt_file_id
            order.status = OrderService.pending
            await session.commit()
            return await OrderService.get_order(order_id)

    @staticmethod
    async def get_order(order_id: int) -> Order | None:
        async with async_session_factory() as session:
            result = await session.execute(
                select(Order)
                .options(
                    selectinload(Order.service),
                    selectinload(Order.plan),
                    selectinload(Order.discount),
                )
                .where(Order.id == order_id)
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def get_user_order(order_id: int, user_id: int) -> Order | None:
        order = await OrderService.get_order(order_id)
        if order is None or order.user_id != user_id:
            return None
        return order

    @staticmethod
    async def list_orders(page: int = 1) -> tuple[list[Order], int]:
        normalized_page = max(page, 1)
        async with async_session_factory() as session:
            count_result = await session.execute(select(func.count(Order.id)))
            total_count = int(count_result.scalar_one())
            result = await session.execute(
                select(Order)
                .options(
                    selectinload(Order.service),
                    selectinload(Order.plan),
                )
                .order_by(Order.id.asc())
                .offset((normalized_page - 1) * OrderService.page_size)
                .limit(OrderService.page_size)
            )
            return list(result.scalars().all()), total_count

    @staticmethod
    async def list_user_orders(user_id: int) -> list[Order]:
        async with async_session_factory() as session:
            result = await session.execute(
                select(Order)
                .options(
                    selectinload(Order.service),
                    selectinload(Order.plan),
                )
                .where(Order.user_id == user_id)
                .order_by(Order.id.desc())
            )
            return list(result.scalars().all())

    @staticmethod
    async def approve_order(order_id: int, config_text: str) -> Order | None:
        normalized_config = OrderService.normalize_config(config_text)
        async with async_session_factory() as session:
            result = await session.execute(
                update(Order)
                .where(Order.id == order_id)
                .values(
                    status=OrderService.approved,
                    config_text=normalized_config,
                    approved_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()
            if not result.rowcount:
                return None
            return await OrderService.get_order(order_id)

    @staticmethod
    async def reject_order(order_id: int) -> Order | None:
        async with async_session_factory() as session:
            result = await session.execute(
                update(Order)
                .where(Order.id == order_id)
                .values(status=OrderService.rejected)
            )
            await session.commit()
            if not result.rowcount:
                return None
            return await OrderService.get_order(order_id)

    @staticmethod
    def normalize_config(config_text: str) -> str:
        normalized_config = config_text.strip()
        if not normalized_config:
            raise ValueError("لینک کانفیگ را ارسال کنید.")
        return normalized_config

    @staticmethod
    def status_label(status: str) -> str:
        labels = {
            OrderService.pending: "در انتظار بررسی",
            OrderService.approved: "تایید شده",
            OrderService.rejected: "رد شده",
        }
        return labels.get(status, status)

    @staticmethod
    def admin_notification_text(order: Order) -> str:
        return (
            "سفارش جدید\n\n"
            "خریدار:\n"
            f"{order.user_id}\n\n"
            "سرویس:\n"
            f"{escape(order.service.name)}\n\n"
            "پلن:\n"
            f"{escape(order.plan.name)}\n\n"
            "مبلغ:\n"
            f"{order.final_price:,} تومان\n\n"
            "شماره سفارش:\n"
            f"{order.id}"
        )

    @staticmethod
    def admin_details_text(order: Order) -> str:
        return (
            f"سفارش: {order.id}\n\n"
            "کاربر:\n"
            f"{order.user_id}\n\n"
            "سرویس:\n"
            f"{escape(order.service.name)}\n\n"
            "پلن:\n"
            f"{escape(order.plan.name)}\n\n"
            "قیمت:\n"
            f"{order.final_price:,} تومان\n\n"
            "تاریخ:\n"
            f"{order.created_at}\n\n"
            "وضعیت:\n"
            f"{OrderService.status_label(order.status)}"
        )

    @staticmethod
    def user_details_text(order: Order) -> str:
        text = (
            "سفارش:\n"
            f"{order.id}\n\n"
            "سرویس:\n"
            f"{escape(order.service.name)}\n\n"
            "پلن:\n"
            f"{escape(order.plan.name)}\n\n"
            "مبلغ:\n"
            f"{order.final_price:,} تومان\n\n"
            "وضعیت:\n"
            f"{OrderService.status_label(order.status)}\n\n"
        )
        if order.status == OrderService.pending:
            return text + "⏳ سفارش شما در حال بررسی است."
        if order.status == OrderService.rejected:
            return text + "❌ سفارش شما رد شده است."
        if order.status == OrderService.approved:
            config_text = escape(order.config_text or "")
        return text + f"✅ سفارش تایید شده است.\n\nکانفیگ:\n\n<code>{escape(config_text)}</code>"
        return text
