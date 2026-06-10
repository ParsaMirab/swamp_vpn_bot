from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.join_required import JOIN_REQUIRED_CHECK_CALLBACK
from bot.keyboards.join_required import join_required_keyboard
from bot.keyboards.user import (
    UserCallback,
    main_menu_keyboard,
    plan_details_keyboard,
    user_order_details_keyboard,
    user_orders_keyboard,
    user_plans_keyboard,
    user_services_keyboard,
)
from bot.config import settings
from bot.keyboards.admin import admin_order_notification_keyboard
from bot.services.bank_card_service import BankCardService
from bot.services.discount_service import DiscountCodeService
from bot.services.order_service import OrderService
from bot.services.plan_service import PlanService
from bot.services.required_channel_service import RequiredChannelService
from bot.services.service_service import ServiceService
from bot.services.setting_service import SettingService
from bot.states.user import UserOrderStates
from bot.services.user_service import UserService

router = Router(name="user_start")
WELCOME_TEXT = """
🌿 به Swamp VPN خوش آمدید

🚀 خرید و مدیریت سرویس‌های شما
⚡ اتصال سریع و پایدار
🔒 امنیت و حریم خصوصی بالا

از منوی زیر گزینه موردنظر خود را انتخاب کنید.
"""


@router.message(CommandStart())
async def start_command(message: Message, state: FSMContext) -> None:
    await state.clear()
    if message.from_user:
        await UserService.register_user(
            user_id=message.from_user.id,
            username=message.from_user.username,
        )
    await message.answer(WELCOME_TEXT, reply_markup=main_menu_keyboard())


@router.callback_query(F.data == JOIN_REQUIRED_CHECK_CALLBACK)
async def join_required_check(callback: CallbackQuery, bot: Bot) -> None:
    if not callback.from_user:
        await callback.answer()
        return

    is_member = await RequiredChannelService.is_user_joined_all_required_channels(
        bot=bot,
        user_id=callback.from_user.id,
    )
    if not is_member:
        channels = await RequiredChannelService.list_channels()
        await callback.answer("هنوز عضو همه کانال‌ها نشده‌اید.", show_alert=True)
        if callback.message:
            try:
                await callback.message.edit_text(
                    "برای استفاده از ربات ابتدا در کانال‌های زیر عضو شوید.",
                    reply_markup=join_required_keyboard(channels),
                )
            except TelegramBadRequest:
                pass
        return

    await callback.answer("عضویت شما تایید شد.")
    if callback.message:
        await callback.message.edit_text(WELCOME_TEXT, reply_markup=main_menu_keyboard())


@router.callback_query(F.data == UserCallback.back_to_main)
async def user_back_to_main(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(WELCOME_TEXT, reply_markup=main_menu_keyboard())


@router.callback_query(F.data == UserCallback.buy_service)
async def buy_service_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    sales_open = await SettingService.is_sales_open()
    if not sales_open:
        await callback.answer()
        if callback.message:
            await callback.message.answer(
                "🔴 فروشگاه در حال حاضر بسته است.\n\n"
                "لطفاً بعداً تلاش کنید."
            )
        return
    services = await ServiceService.list_services()
    await callback.answer()
    if not callback.message:
        return

    if not services:
        await callback.message.edit_text("در حال حاضر سرویسی برای خرید ثبت نشده است.", reply_markup=main_menu_keyboard())
        return

    await callback.message.edit_text("سرویس موردنظر را انتخاب کنید.", reply_markup=user_services_keyboard(services))


@router.callback_query(F.data.startswith("user:buy:service:"))
async def buy_service_plans(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    service_id = _parse_callback_int(callback.data)
    if service_id is None:
        await callback.answer()
        return

    service = await ServiceService.get_service(service_id)
    if service is None:
        await callback.answer("سرویس پیدا نشد", show_alert=True)
        return

    plans = await PlanService.list_plans(service_id)
    await callback.answer()
    if not callback.message:
        return

    if not plans:
        await callback.message.edit_text(
            "برای این سرویس هنوز پلنی ثبت نشده است.",
            reply_markup=user_services_keyboard(await ServiceService.list_services()),
        )
        return

    await callback.message.edit_text(
        f"پلن سرویس «{escape(service.name)}» را انتخاب کنید.",
        reply_markup=user_plans_keyboard(service_id, plans),
    )


@router.callback_query(F.data.startswith("user:buy:plan:"))
async def buy_plan_selected(callback: CallbackQuery, state: FSMContext) -> None:
    service_id, plan_id = _parse_plan_callback(callback.data)
    if service_id is None or plan_id is None:
        await callback.answer()
        return

    plan = await PlanService.get_plan(plan_id=plan_id, service_id=service_id)
    if plan is None:
        await callback.answer("پلن پیدا نشد", show_alert=True)
        return

    await state.update_data(
        service_id=service_id,
        plan_id=plan_id,
        discount_id=None,
        original_price=plan.price,
        final_price=plan.price,
    )
    await state.set_state(None)
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            _plan_details_text(service_name=plan.service.name, plan_name=plan.name, original_price=plan.price),
            reply_markup=plan_details_keyboard(service_id),
        )


@router.callback_query(F.data == UserCallback.enter_discount)
async def enter_discount_start(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if not isinstance(data.get("plan_id"), int):
        await callback.answer("ابتدا یک پلن انتخاب کنید.", show_alert=True)
        return

    await state.set_state(UserOrderStates.waiting_for_discount_code)
    await callback.answer()
    if callback.message:
        await callback.message.answer("کد تخفیف را وارد کنید")


@router.message(UserOrderStates.waiting_for_discount_code)
async def enter_discount_finish(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    service_id = data.get("service_id")
    plan_id = data.get("plan_id")
    if not message.from_user or not isinstance(service_id, int) or not isinstance(plan_id, int):
        await state.clear()
        await message.answer(DiscountCodeService.invalid_message)
        return

    plan = await PlanService.get_plan(plan_id=plan_id, service_id=service_id)
    if plan is None or not message.text:
        await message.answer(DiscountCodeService.invalid_message)
        return

    try:
        discount, final_price = await DiscountCodeService.apply_discount(
            code=message.text,
            user_id=message.from_user.id,
            plan_price=plan.price,
        )
    except ValueError:
        await message.answer(DiscountCodeService.invalid_message)
        return

    await state.update_data(
        discount_id=discount.id,
        original_price=plan.price,
        final_price=final_price,
    )
    await state.set_state(None)
    await message.answer(
        _plan_details_text(
            service_name=plan.service.name,
            plan_name=plan.name,
            original_price=plan.price,
            final_price=final_price,
        ),
        reply_markup=plan_details_keyboard(service_id),
    )


@router.callback_query(F.data == UserCallback.register_order)
async def register_order(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user:
        await callback.answer()
        return

    sales_open = await SettingService.is_sales_open()
    if not sales_open:
        await callback.answer()
        if callback.message:
            await callback.message.answer(
                "🔴 فروشگاه در حال حاضر بسته است.\n\n"
                "لطفاً بعداً تلاش کنید."
            )
        return

    data = await state.get_data()
    service_id = data.get("service_id")
    plan_id = data.get("plan_id")
    discount_id = data.get("discount_id")
    if not isinstance(service_id, int) or not isinstance(plan_id, int):
        await callback.answer("ابتدا یک پلن انتخاب کنید.", show_alert=True)
        return

    plan = await PlanService.get_plan(plan_id=plan_id, service_id=service_id)
    if plan is None:
        await callback.answer("پلن پیدا نشد", show_alert=True)
        return

    card = await BankCardService.get_first_card()
    if card is None:
        await callback.answer("کارت بانکی برای پرداخت ثبت نشده است.", show_alert=True)
        return

    original_price = plan.price
    final_price = data.get("final_price")
    if not isinstance(final_price, int):
        final_price = original_price
    if not isinstance(discount_id, int):
        discount_id = None

    await state.update_data(
        service_id=service_id,
        plan_id=plan_id,
        discount_id=discount_id,
        original_price=original_price,
        final_price=final_price,
    )
    await state.set_state(UserOrderStates.waiting_for_receipt)
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            _invoice_text(
                service_name=plan.service.name,
                plan_name=plan.name,
                final_price=final_price,
                card_number=card.card_number,
                owner_name=card.owner_name,
            )
        )


@router.message(UserOrderStates.waiting_for_receipt)
async def receipt_upload(message: Message, state: FSMContext, bot: Bot) -> None:
    sales_open = await SettingService.is_sales_open()
    if not sales_open:
        await state.clear()
        await message.answer(
            "🔴 فروشگاه در حال حاضر بسته است.\n\n"
            "لطفاً بعداً تلاش کنید."
        )
        return

    data = await state.get_data()
    service_id = data.get("service_id")
    plan_id = data.get("plan_id")
    discount_id = data.get("discount_id")
    original_price = data.get("original_price")
    final_price = data.get("final_price")
    if (
        not message.from_user
        or not isinstance(service_id, int)
        or not isinstance(plan_id, int)
        or not isinstance(original_price, int)
        or not isinstance(final_price, int)
    ):
        await state.clear()
        await message.answer("سفارش معتبر نیست.")
        return

    if not message.photo:
        await message.answer("لطفاً تصویر فیش واریزی را ارسال نمایید.")
        return

    receipt_file_id = message.photo[-1].file_id
    if not isinstance(discount_id, int):
        discount_id = None

    updated = await OrderService.create_order(
        user_id=message.from_user.id,
        service_id=service_id,
        plan_id=plan_id,
        discount_id=discount_id,
        original_price=original_price,
        final_price=final_price,
        receipt_file_id=receipt_file_id,
    )
    await state.clear()
    try:
        await bot.send_message(
            chat_id=settings.admin_id,
            text=OrderService.admin_notification_text(updated),
            reply_markup=admin_order_notification_keyboard(updated.id),
        )
    except TelegramAPIError:
        pass
    await message.answer("✅ سفارش شما ثبت شد.\n\n⏳ سفارش شما در حال بررسی و پیگیری است.")


@router.callback_query(F.data == UserCallback.my_services)
async def my_orders(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if not callback.from_user:
        await callback.answer()
        return
    orders = await OrderService.list_user_orders(callback.from_user.id)
    await callback.answer()
    if not callback.message:
        return
    if not orders:
        await callback.message.edit_text("سفارش‌های من\n\nهنوز سفارشی ثبت نکرده‌اید.", reply_markup=main_menu_keyboard())
        return
    await callback.message.edit_text("سفارش‌های من", reply_markup=user_orders_keyboard(orders))


@router.callback_query(F.data.startswith("user:orders:view:"))
async def my_order_details(callback: CallbackQuery) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    order_id = _parse_callback_int(callback.data)
    if order_id is None:
        await callback.answer()
        return
    order = await OrderService.get_user_order(order_id=order_id, user_id=callback.from_user.id)
    if order is None:
        await callback.answer("سفارش پیدا نشد", show_alert=True)
        return
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            OrderService.user_details_text(order),
            reply_markup=user_order_details_keyboard(),
        )


def _plan_details_text(
    service_name: str,
    plan_name: str,
    original_price: int,
    final_price: int | None = None,
) -> str:
    if final_price is None:
        return (
            f"نوع سرویس: {escape(service_name)}\n\n"
            f"حجم: {escape(plan_name)}\n"
            "⏰ مدت: 30 روزه\n\n"
            "قیمت این سرویس:\n\n"
            f"{original_price:,} تومان"
        )

    return (
        f"نوع سرویس: {escape(service_name)}\n\n"
        f"حجم: {escape(plan_name)}\n"
        "⏰ مدت: 30 روزه\n\n"
        "قیمت قبلی:\n"
        f"<s>{original_price:,} تومان</s>\n\n"
        "✅ قیمت بعد از تخفیف:\n"
        f"{final_price:,} تومان"
    )


def _invoice_text(
    service_name: str,
    plan_name: str,
    final_price: int,
    card_number: str,
    owner_name: str,
) -> str:
    return (
        "🧾 <b>فاکتور سفارش</b>\n\n"
        "🌐 <b>سرویس:</b>\n"
        f"{escape(service_name)}\n\n"
        "💎 <b>پلن:</b>\n"
        f"{escape(plan_name)}\n\n"
        "💰 <b>مبلغ قابل پرداخت:</b>\n"
        f"<b>{final_price:,}</b> تومان\n\n"
        "💳 <b>لطفاً مبلغ را به شماره کارت زیر واریز کنید:</b>\n\n"
        f"<code>{escape(card_number)}</code>\n"
        f"👤 {escape(owner_name)}\n\n"
        "📸 سپس تصویر فیش واریزی را ارسال نمایید."
    )


def _parse_callback_int(callback_data: str | None) -> int | None:
    if not callback_data:
        return None
    value = callback_data.rsplit(":", maxsplit=1)[-1]
    if not value.isdigit():
        return None
    return int(value)


def _parse_plan_callback(callback_data: str | None) -> tuple[int | None, int | None]:
    if not callback_data:
        return None, None
    parts = callback_data.rsplit(":", maxsplit=2)
    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
        return None, None
    return int(parts[1]), int(parts[2])
