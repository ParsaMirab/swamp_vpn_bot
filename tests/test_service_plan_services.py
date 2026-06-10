import os
import tempfile
import unittest

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import bot.services.bank_card_service as bank_card_service_module
import bot.services.discount_service as discount_service_module
import bot.services.order_service as order_service_module
import bot.services.plan_service as plan_service_module
import bot.services.service_service as service_service_module
from bot.database.base import Base
from bot.services.bank_card_service import BankCardService
from bot.services.discount_service import DiscountCodeService
from bot.services.order_service import OrderService
from bot.services.plan_service import PlanService
from bot.services.service_service import ServiceService


class ServicePlanServicesTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        fd, self.database_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{self.database_path}")
        self.session_factory = async_sessionmaker(bind=self.engine, expire_on_commit=False)
        self.original_service_session_factory = service_service_module.async_session_factory
        self.original_plan_session_factory = plan_service_module.async_session_factory
        self.original_bank_card_session_factory = bank_card_service_module.async_session_factory
        self.original_discount_session_factory = discount_service_module.async_session_factory
        self.original_order_session_factory = order_service_module.async_session_factory
        service_service_module.async_session_factory = self.session_factory
        plan_service_module.async_session_factory = self.session_factory
        bank_card_service_module.async_session_factory = self.session_factory
        discount_service_module.async_session_factory = self.session_factory
        order_service_module.async_session_factory = self.session_factory

        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def asyncTearDown(self) -> None:
        service_service_module.async_session_factory = self.original_service_session_factory
        plan_service_module.async_session_factory = self.original_plan_session_factory
        bank_card_service_module.async_session_factory = self.original_bank_card_session_factory
        discount_service_module.async_session_factory = self.original_discount_session_factory
        order_service_module.async_session_factory = self.original_order_session_factory
        await self.engine.dispose()
        os.unlink(self.database_path)

    async def test_service_delete_removes_related_plans(self) -> None:
        service = await ServiceService.create_service("اینترنت ملی")
        await PlanService.create_plan(service_id=service.id, name="یک ماهه", price=250000)
        await PlanService.create_plan(service_id=service.id, name="سه ماهه", price=650000)

        plans = await PlanService.list_plans(service.id)
        self.assertEqual([plan.name for plan in plans], ["یک ماهه", "سه ماهه"])
        self.assertEqual([plan.price for plan in plans], [250000, 650000])

        deleted = await ServiceService.delete_service(service.id)

        self.assertTrue(deleted)
        self.assertEqual(await PlanService.list_plans(service.id), [])

    async def test_service_delete_removes_related_orders(self) -> None:
        service = await ServiceService.create_service("VPN")
        plan = await PlanService.create_plan(service_id=service.id, name="100 GB", price=250000)
        order = await OrderService.create_order(
            user_id=123456789,
            service_id=service.id,
            plan_id=plan.id,
            original_price=250000,
            final_price=250000,
            receipt_file_id="telegram-file-id",
        )

        deleted = await ServiceService.delete_service(service.id)

        self.assertTrue(deleted)
        self.assertIsNone(await OrderService.get_order(order.id))
        self.assertEqual(await PlanService.list_plans(service.id), [])

    async def test_bank_card_create_list_delete(self) -> None:
        card = await BankCardService.create_card(
            card_number="6037 9999 9999 1234",
            owner_name="علی رضایی",
        )

        cards = await BankCardService.list_cards()
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0].card_number, "6037999999991234")
        self.assertEqual(BankCardService.mask_card_number(card.card_number), "6037********1234")

        deleted = await BankCardService.delete_card(card.id)

        self.assertTrue(deleted)
        self.assertEqual(await BankCardService.list_cards(), [])

    async def test_discount_apply_tracks_usage_and_prevents_reuse(self) -> None:
        discount = await DiscountCodeService.create_discount(
            code="swamp50",
            usage_limit=1,
            per_user_usage_limit=1,
            discount_amount=100000,
        )

        applied_discount, final_price = await DiscountCodeService.apply_discount(
            code="SWAMP50",
            user_id=123456789,
            plan_price=250000,
        )

        self.assertEqual(applied_discount.id, discount.id)
        self.assertEqual(final_price, 150000)
        discounts = await DiscountCodeService.list_discounts()
        self.assertEqual(discounts[0].used_count, 1)
        self.assertEqual([usage.user_id for usage in discounts[0].usages], [123456789])

        with self.assertRaises(ValueError):
            await DiscountCodeService.apply_discount(
                code="SWAMP50",
                user_id=123456789,
                plan_price=250000,
            )

        with self.assertRaises(ValueError):
            await DiscountCodeService.apply_discount(
                code="SWAMP50",
                user_id=555555555,
                plan_price=250000,
            )

    async def test_discount_per_user_limit(self) -> None:
        discount = await DiscountCodeService.create_discount(
            code="MULTI",
            usage_limit=10,
            per_user_usage_limit=2,
            discount_amount=50000,
        )

        price_a = await DiscountCodeService.apply_discount(
            code="MULTI", user_id=100, plan_price=200000,
        )
        self.assertEqual(price_a[1], 150000)

        price_b = await DiscountCodeService.apply_discount(
            code="MULTI", user_id=100, plan_price=300000,
        )
        self.assertEqual(price_b[1], 250000)

        with self.assertRaises(ValueError):
            await DiscountCodeService.apply_discount(
                code="MULTI", user_id=100, plan_price=200000,
            )

        result_c = await DiscountCodeService.apply_discount(
            code="MULTI", user_id=200, plan_price=200000,
        )
        self.assertEqual(result_c[1], 150000)
        discounts = await DiscountCodeService.list_discounts()
        self.assertEqual(discounts[0].used_count, 3)

    async def test_discount_expiration(self) -> None:
        from datetime import datetime, timedelta, timezone

        expired = await DiscountCodeService.create_discount(
            code="EXPIRED",
            usage_limit=10,
            per_user_usage_limit=5,
            discount_amount=50000,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )

        with self.assertRaises(ValueError):
            await DiscountCodeService.apply_discount(
                code="EXPIRED", user_id=100, plan_price=200000,
            )

        valid = await DiscountCodeService.create_discount(
            code="VALID",
            usage_limit=10,
            per_user_usage_limit=5,
            discount_amount=50000,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )

        result = await DiscountCodeService.apply_discount(
            code="VALID", user_id=100, plan_price=200000,
        )
        self.assertEqual(result[1], 150000)

    async def test_order_create_and_attach_receipt(self) -> None:
        service = await ServiceService.create_service("اینترنت ملی")
        plan = await PlanService.create_plan(service_id=service.id, name="100 گیگ", price=250000)
        discount = await DiscountCodeService.create_discount("VIP100", usage_limit=10, per_user_usage_limit=1, discount_amount=100000)

        order = await OrderService.create_order(
            user_id=123456789,
            service_id=service.id,
            plan_id=plan.id,
            discount_id=discount.id,
            original_price=250000,
            final_price=150000,
        )
        updated = await OrderService.attach_receipt(
            order_id=order.id,
            user_id=123456789,
            receipt_file_id="telegram-file-id",
        )
        stored_order = await OrderService.get_order(order.id)

        self.assertTrue(updated)
        self.assertIsNotNone(stored_order)
        self.assertEqual(stored_order.receipt_file_id, "telegram-file-id")
        self.assertEqual(stored_order.status, OrderService.pending)

    async def test_order_create_returns_notification_ready_order(self) -> None:
        service = await ServiceService.create_service("Ø§ÛŒÙ†ØªØ±Ù†Øª Ù…Ù„ÛŒ")
        plan = await PlanService.create_plan(service_id=service.id, name="100 Ú¯ÛŒÚ¯", price=250000)

        order = await OrderService.create_order(
            user_id=123456789,
            service_id=service.id,
            plan_id=plan.id,
            original_price=250000,
            final_price=250000,
            receipt_file_id="telegram-file-id",
        )
        notification_text = OrderService.admin_notification_text(order)

        self.assertIn(str(order.id), notification_text)
        self.assertIn(str(order.user_id), notification_text)
        self.assertIn(service.name, notification_text)
        self.assertIn(plan.name, notification_text)


if __name__ == "__main__":
    unittest.main()
