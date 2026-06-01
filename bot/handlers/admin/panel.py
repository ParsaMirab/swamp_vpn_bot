from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import settings
from bot.filters.admin import AdminFilter
from bot.keyboards.admin import (
    AdminCallback,
    admin_order_details_keyboard,
    admin_orders_keyboard,
    admin_panel_keyboard,
    delete_cards_keyboard,
    delete_channels_keyboard,
    delete_discounts_keyboard,
    delete_plans_keyboard,
    delete_services_keyboard,
    discount_codes_keyboard,
    financial_management_keyboard,
    join_require_keyboard,
    plan_management_keyboard,
    plan_services_keyboard,
    service_management_keyboard,
)
from bot.services.bank_card_service import BankCardService
from bot.services.discount_service import DiscountCodeService
from bot.services.order_service import OrderService
from bot.services.plan_service import PlanService
from bot.services.required_channel_service import RequiredChannelService
from bot.services.service_service import ServiceService
from bot.states.admin import AdminOrderStates, BankCardStates, DiscountCodeStates, JoinRequireStates, PlanStates, ServiceStates

router = Router(name="admin_panel")


@router.message(Command("admin"))
async def admin_command(message: Message, state: FSMContext) -> None:
    await state.clear()
    if not message.from_user or message.from_user.id != settings.admin_id:
        return
    await message.answer("پنل مدیریت", reply_markup=admin_panel_keyboard())


@router.callback_query(AdminFilter(), F.data == AdminCallback.join_require)
async def join_require_panel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _answer_join_require_panel(callback)


@router.callback_query(AdminFilter(), F.data == AdminCallback.join_back)
async def join_require_back(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("پنل مدیریت", reply_markup=admin_panel_keyboard())


@router.callback_query(AdminFilter(), F.data == AdminCallback.orders)
async def orders_panel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _answer_orders_page(callback, page=1)


@router.callback_query(AdminFilter(), F.data.startswith("admin:orders:page:"))
async def orders_page(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    page = _parse_callback_int(callback.data) or 1
    await _answer_orders_page(callback, page=page)


@router.callback_query(AdminFilter(), F.data == AdminCallback.orders_back)
async def orders_back(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("پنل مدیریت", reply_markup=admin_panel_keyboard())


@router.callback_query(AdminFilter(), F.data.startswith("admin:orders:view:"))
async def order_details(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    order_id = _parse_callback_int(callback.data)
    if order_id is None:
        await callback.answer()
        return
    await _answer_order_details(callback, order_id)


@router.callback_query(AdminFilter(), F.data.startswith("admin:orders:approve:"))
async def approve_order_start(callback: CallbackQuery, state: FSMContext) -> None:
    order_id = _parse_callback_int(callback.data)
    if order_id is None:
        await callback.answer()
        return
    order = await OrderService.get_order(order_id)
    if order is None:
        await callback.answer("سفارش پیدا نشد", show_alert=True)
        return
    await state.set_state(AdminOrderStates.waiting_for_config)
    await state.update_data(order_id=order_id)
    await callback.answer()
    if callback.message:
        await callback.message.answer("لینک کانفیگ را ارسال کنید")


@router.message(AdminFilter(), AdminOrderStates.waiting_for_config)
async def approve_order_finish(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    order_id = data.get("order_id")
    if not isinstance(order_id, int):
        await state.clear()
        await message.answer("سفارش معتبر نیست.")
        return
    if not message.text:
        await message.answer("لینک کانفیگ را ارسال کنید.")
        return

    try:
        order = await OrderService.approve_order(order_id=order_id, config_text=message.text)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await state.clear()
    if order is None:
        await message.answer("سفارش پیدا نشد.")
        return

    try:
        await bot.send_message(
            chat_id=order.user_id,
            text=(
                "✅ سفارش شما تایید شد.\n\n"
                "کانفیگ شما:\n\n"
                f"{escape(order.config_text or '')}\n\n"
                "از بخش «سفارش‌های من» می‌توانید مجدداً آن را مشاهده کنید."
            ),
        )
        await message.answer("سفارش تایید شد و کانفیگ برای خریدار ارسال شد.")
    except TelegramAPIError:
        await message.answer("سفارش تایید شد، اما ارسال پیام به خریدار ناموفق بود.")
    await message.answer(OrderService.admin_details_text(order), reply_markup=admin_order_details_keyboard(order.id))


@router.callback_query(AdminFilter(), F.data.startswith("admin:orders:reject:"))
async def reject_order(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    order_id = _parse_callback_int(callback.data)
    if order_id is None:
        await callback.answer()
        return
    order = await OrderService.reject_order(order_id)
    if order is None:
        await callback.answer("سفارش پیدا نشد", show_alert=True)
        return
    try:
        await bot.send_message(
            chat_id=order.user_id,
            text="❌ سفارش شما رد شد.\n\nدر صورت وجود مشکل با پشتیبانی تماس بگیرید.",
        )
    except TelegramAPIError:
        pass
    await callback.answer("سفارش رد شد")
    if callback.message:
        await callback.message.edit_text(
            OrderService.admin_details_text(order),
            reply_markup=admin_order_details_keyboard(order.id),
        )


@router.callback_query(AdminFilter(), F.data == AdminCallback.back)
async def admin_back(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("به منوی اصلی برگشتید.")


@router.callback_query(AdminFilter(), F.data == AdminCallback.add_channel)
async def add_channel_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(JoinRequireStates.waiting_for_channel)
    if callback.message:
        await callback.message.answer("channel_id یا username کانال را ارسال کنید.")
    await callback.answer()


@router.message(AdminFilter(), JoinRequireStates.waiting_for_channel)
async def add_channel_finish(message: Message, state: FSMContext, bot: Bot) -> None:
    if not message.text:
        await message.answer("channel_id یا username کانال را به‌صورت متن ارسال کنید.")
        return
    try:
        channel_input = await RequiredChannelService.resolve_channel(bot, message.text)
        await RequiredChannelService.ensure_membership_check_available(
            bot=bot,
            channel_id=channel_input.channel_id,
            channel_username=channel_input.channel_username,
            probe_user_id=settings.admin_id,
        )
    except ValueError as exc:
        await message.answer(str(exc))
        return

    channel = await RequiredChannelService.add_channel(
        channel_id=channel_input.channel_id,
        channel_username=channel_input.channel_username,
    )
    await state.clear()
    await message.answer(f"کانال {RequiredChannelService.get_channel_title(channel)} ذخیره شد.")
    await message.answer(await _join_require_text(), reply_markup=join_require_keyboard())


@router.callback_query(AdminFilter(), F.data == AdminCallback.delete_channel_menu)
async def delete_channel_menu(callback: CallbackQuery) -> None:
    channels = await RequiredChannelService.list_channels()
    await callback.answer()
    if not callback.message:
        return
    if not channels:
        await callback.message.edit_text("هیچ کانالی ثبت نشده است.", reply_markup=join_require_keyboard())
        return
    await callback.message.edit_text("برای حذف، کانال موردنظر را انتخاب کنید.", reply_markup=delete_channels_keyboard(channels))


@router.callback_query(AdminFilter(), F.data.startswith("admin:join:delete:"))
async def delete_channel(callback: CallbackQuery) -> None:
    channel_id = _parse_callback_int(callback.data)
    if channel_id is None:
        await callback.answer()
        return
    deleted = await RequiredChannelService.delete_channel(channel_id)
    await _answer_join_require_panel(callback, answer_text="حذف شد" if deleted else "کانال پیدا نشد")


@router.callback_query(AdminFilter(), F.data == AdminCallback.add_service)
async def service_management_panel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(await _service_management_text(), reply_markup=service_management_keyboard())


@router.callback_query(AdminFilter(), F.data == AdminCallback.service_back)
async def service_management_back(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("پنل مدیریت", reply_markup=admin_panel_keyboard())


@router.callback_query(AdminFilter(), F.data == AdminCallback.service_add)
async def add_service_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ServiceStates.waiting_for_name)
    await callback.answer()
    if callback.message:
        await callback.message.answer("نام سرویس را ارسال کنید")


@router.message(AdminFilter(), ServiceStates.waiting_for_name)
async def add_service_finish(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("نام سرویس را به‌صورت متن ارسال کنید.")
        return
    try:
        service = await ServiceService.create_service(message.text)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await state.clear()
    await message.answer(f"سرویس «{escape(service.name)}» ذخیره شد.")
    await message.answer(await _service_management_text(), reply_markup=service_management_keyboard())


@router.callback_query(AdminFilter(), F.data == AdminCallback.service_delete_menu)
async def delete_service_menu(callback: CallbackQuery) -> None:
    services = await ServiceService.list_services()
    await callback.answer()
    if not callback.message:
        return
    if not services:
        await callback.message.edit_text("هیچ سرویسی ثبت نشده است.", reply_markup=service_management_keyboard())
        return
    await callback.message.edit_text("برای حذف سرویس، یک مورد را انتخاب کنید.", reply_markup=delete_services_keyboard(services))


@router.callback_query(AdminFilter(), F.data.startswith("admin:service:delete:"))
async def delete_service(callback: CallbackQuery) -> None:
    service_id = _parse_callback_int(callback.data)
    if service_id is None:
        await callback.answer()
        return
    deleted = await ServiceService.delete_service(service_id)
    await callback.answer("حذف شد" if deleted else "سرویس پیدا نشد")
    if callback.message:
        await callback.message.edit_text(await _service_management_text(), reply_markup=service_management_keyboard())


@router.callback_query(AdminFilter(), F.data == AdminCallback.service_list)
async def service_list(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(await _service_list_text(), reply_markup=service_management_keyboard())


@router.callback_query(AdminFilter(), F.data == AdminCallback.add_plan)
async def plan_services_panel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    services = await ServiceService.list_services()
    await callback.answer()
    if not callback.message:
        return
    if not services:
        await callback.message.edit_text("برای مدیریت پلن‌ها ابتدا یک سرویس ثبت کنید.", reply_markup=admin_panel_keyboard())
        return
    await callback.message.edit_text("سرویس موردنظر را انتخاب کنید.", reply_markup=plan_services_keyboard(services))


@router.callback_query(AdminFilter(), F.data == AdminCallback.plans_back)
async def plan_services_back(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("پنل مدیریت", reply_markup=admin_panel_keyboard())


@router.callback_query(AdminFilter(), F.data.startswith("admin:plans:service:"))
async def plan_management_panel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    service_id = _parse_callback_int(callback.data)
    if service_id is None:
        await callback.answer()
        return
    await _answer_plan_management_panel(callback, service_id)


@router.callback_query(AdminFilter(), F.data.startswith("admin:plans:add:"))
async def add_plan_start(callback: CallbackQuery, state: FSMContext) -> None:
    service_id = _parse_callback_int(callback.data)
    if service_id is None:
        await callback.answer()
        return
    service = await ServiceService.get_service(service_id)
    if service is None:
        await callback.answer("سرویس پیدا نشد", show_alert=True)
        return
    await state.set_state(PlanStates.waiting_for_name)
    await state.update_data(service_id=service_id)
    await callback.answer()
    if callback.message:
        await callback.message.answer("نام پلن را ارسال کنید")


@router.message(AdminFilter(), PlanStates.waiting_for_name)
async def add_plan_name(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("نام پلن را به‌صورت متن ارسال کنید.")
        return
    try:
        plan_name = PlanService.normalize_name(message.text)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(plan_name=plan_name)
    await state.set_state(PlanStates.waiting_for_price)
    await message.answer("قیمت پلن را ارسال کنید")


@router.message(AdminFilter(), PlanStates.waiting_for_price)
async def add_plan_finish(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    service_id = data.get("service_id")
    plan_name = data.get("plan_name")
    if not isinstance(service_id, int) or not isinstance(plan_name, str):
        await state.clear()
        await message.answer("سرویس انتخاب‌شده معتبر نیست.")
        return
    if not message.text:
        await message.answer("قیمت پلن را به‌صورت عدد ارسال کنید.")
        return
    try:
        price = PlanService.parse_price(message.text)
        plan = await PlanService.create_plan(service_id=service_id, name=plan_name, price=price)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await state.clear()
    await message.answer(f"پلن «{escape(plan.name)}» با قیمت {plan.price:,} تومان ذخیره شد.")
    service = await ServiceService.get_service(service_id)
    if service is not None:
        plan_count = await PlanService.count_plans(service_id)
        await message.answer(_plan_management_text(service.name, plan_count), reply_markup=plan_management_keyboard(service_id))


@router.callback_query(AdminFilter(), F.data.startswith("admin:plans:delete_menu:"))
async def delete_plan_menu(callback: CallbackQuery) -> None:
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
        await callback.message.edit_text("هیچ پلنی برای این سرویس ثبت نشده است.", reply_markup=plan_management_keyboard(service_id))
        return
    await callback.message.edit_text(f"حذف پلن از سرویس «{escape(service.name)}»:", reply_markup=delete_plans_keyboard(service_id, plans))


@router.callback_query(AdminFilter(), F.data.startswith("admin:plans:delete:"))
async def delete_plan(callback: CallbackQuery) -> None:
    parts = callback.data.rsplit(":", maxsplit=2) if callback.data else []
    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
        await callback.answer()
        return
    service_id = int(parts[1])
    plan_id = int(parts[2])
    deleted = await PlanService.delete_plan(plan_id=plan_id, service_id=service_id)
    await _answer_plan_management_panel(callback, service_id, answer_text="پلن حذف شد" if deleted else "پلن پیدا نشد")


@router.callback_query(AdminFilter(), F.data == AdminCallback.financial_management)
async def financial_management_panel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _answer_financial_management_panel(callback)


@router.callback_query(AdminFilter(), F.data == AdminCallback.card_back)
async def financial_management_back(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("پنل مدیریت", reply_markup=admin_panel_keyboard())


@router.callback_query(AdminFilter(), F.data == AdminCallback.card_add)
async def add_card_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(BankCardStates.waiting_for_card_number)
    await callback.answer()
    if callback.message:
        await callback.message.answer("شماره کارت را ارسال کنید")


@router.message(AdminFilter(), BankCardStates.waiting_for_card_number)
async def add_card_number(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("شماره کارت را به‌صورت متن ارسال کنید.")
        return
    try:
        card_number = BankCardService.normalize_card_number(message.text)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(card_number=card_number)
    await state.set_state(BankCardStates.waiting_for_owner_name)
    await message.answer("نام صاحب کارت را ارسال کنید")


@router.message(AdminFilter(), BankCardStates.waiting_for_owner_name)
async def add_card_finish(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    card_number = data.get("card_number")
    if not isinstance(card_number, str):
        await state.clear()
        await message.answer("شماره کارت معتبر نیست.")
        return
    if not message.text:
        await message.answer("نام صاحب کارت را به‌صورت متن ارسال کنید.")
        return
    try:
        card = await BankCardService.create_card(card_number=card_number, owner_name=message.text)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await state.clear()
    await message.answer(f"کارت {BankCardService.mask_card_number(card.card_number)} ذخیره شد.")
    await message.answer(_financial_management_text(), reply_markup=financial_management_keyboard())


@router.callback_query(AdminFilter(), F.data == AdminCallback.card_delete_menu)
async def delete_card_menu(callback: CallbackQuery) -> None:
    cards = await BankCardService.list_cards()
    await callback.answer()
    if not callback.message:
        return
    if not cards:
        await callback.message.edit_text("هیچ کارتی ثبت نشده است.", reply_markup=financial_management_keyboard())
        return
    await callback.message.edit_text("برای حذف کارت، یک مورد را انتخاب کنید.", reply_markup=delete_cards_keyboard(cards))


@router.callback_query(AdminFilter(), F.data.startswith("admin:cards:delete:"))
async def delete_card(callback: CallbackQuery) -> None:
    card_id = _parse_callback_int(callback.data)
    if card_id is None:
        await callback.answer()
        return
    deleted = await BankCardService.delete_card(card_id)
    await _answer_financial_management_panel(callback, answer_text="کارت حذف شد" if deleted else "کارت پیدا نشد")


@router.callback_query(AdminFilter(), F.data == AdminCallback.card_list)
async def card_list(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(await _card_list_text(), reply_markup=financial_management_keyboard())


@router.callback_query(AdminFilter(), F.data == AdminCallback.discount_codes)
async def discount_codes_panel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await _answer_discount_codes_panel(callback)


@router.callback_query(AdminFilter(), F.data == AdminCallback.discount_back)
async def discount_codes_back(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if callback.message:
        await callback.message.edit_text("پنل مدیریت", reply_markup=admin_panel_keyboard())


@router.callback_query(AdminFilter(), F.data == AdminCallback.discount_create)
async def create_discount_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(DiscountCodeStates.waiting_for_code)
    await callback.answer()
    if callback.message:
        await callback.message.answer("کد تخفیف را ارسال کنید")


@router.message(AdminFilter(), DiscountCodeStates.waiting_for_code)
async def create_discount_code(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("کد تخفیف را به‌صورت متن ارسال کنید.")
        return
    try:
        code = DiscountCodeService.normalize_code(message.text)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(discount_code=code)
    await state.set_state(DiscountCodeStates.waiting_for_usage_limit)
    await message.answer("این کد چند بار قابل استفاده باشد؟")


@router.message(AdminFilter(), DiscountCodeStates.waiting_for_usage_limit)
async def create_discount_usage_limit(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("سقف استفاده را به‌صورت عدد ارسال کنید.")
        return
    try:
        usage_limit = DiscountCodeService.parse_positive_int(message.text, "سقف استفاده باید عدد مثبت باشد.")
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(usage_limit=usage_limit)
    await state.set_state(DiscountCodeStates.waiting_for_discount_amount)
    await message.answer("مبلغ تخفیف را به تومان وارد کنید")


@router.message(AdminFilter(), DiscountCodeStates.waiting_for_discount_amount)
async def create_discount_finish(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    code = data.get("discount_code")
    usage_limit = data.get("usage_limit")
    if not isinstance(code, str) or not isinstance(usage_limit, int):
        await state.clear()
        await message.answer("اطلاعات کد تخفیف معتبر نیست.")
        return
    if not message.text:
        await message.answer("مبلغ تخفیف را به‌صورت عدد ارسال کنید.")
        return
    try:
        discount_amount = DiscountCodeService.parse_positive_int(message.text, "مبلغ تخفیف باید عدد مثبت باشد.")
        discount = await DiscountCodeService.create_discount(code, usage_limit, discount_amount)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await state.clear()
    await message.answer(f"کد تخفیف «{escape(discount.code)}» ذخیره شد.")
    await message.answer(_discount_codes_text(), reply_markup=discount_codes_keyboard())


@router.callback_query(AdminFilter(), F.data == AdminCallback.discount_list)
async def discount_list(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(await _discount_list_text(), reply_markup=discount_codes_keyboard())


@router.callback_query(AdminFilter(), F.data == AdminCallback.discount_delete_menu)
async def delete_discount_menu(callback: CallbackQuery) -> None:
    discounts = await DiscountCodeService.list_discounts()
    await callback.answer()
    if not callback.message:
        return
    if not discounts:
        await callback.message.edit_text("هیچ کد تخفیفی ثبت نشده است.", reply_markup=discount_codes_keyboard())
        return
    await callback.message.edit_text("برای حذف کد تخفیف، یک مورد را انتخاب کنید.", reply_markup=delete_discounts_keyboard(discounts))


@router.callback_query(AdminFilter(), F.data.startswith("admin:discounts:delete:"))
async def delete_discount(callback: CallbackQuery) -> None:
    discount_id = _parse_callback_int(callback.data)
    if discount_id is None:
        await callback.answer()
        return
    deleted = await DiscountCodeService.delete_discount(discount_id)
    await _answer_discount_codes_panel(callback, answer_text="کد تخفیف حذف شد" if deleted else "کد تخفیف پیدا نشد")


async def _answer_orders_page(callback: CallbackQuery, page: int, answer_text: str | None = None) -> None:
    orders, total_count = await OrderService.list_orders(page)
    await callback.answer(answer_text)
    if not callback.message:
        return
    if not orders:
        await callback.message.edit_text("سفارش‌ها\n\nهیچ سفارشی ثبت نشده است.", reply_markup=admin_panel_keyboard())
        return
    await callback.message.edit_text(
        "سفارش‌ها",
        reply_markup=admin_orders_keyboard(orders=orders, page=max(page, 1), total_count=total_count),
    )


async def _answer_order_details(callback: CallbackQuery, order_id: int) -> None:
    order = await OrderService.get_order(order_id)
    if order is None:
        await callback.answer("سفارش پیدا نشد", show_alert=True)
        return
    await callback.answer()
    if not callback.message:
        return
    if order.receipt_file_id:
        await callback.message.answer_photo(photo=order.receipt_file_id, caption="فیش پرداخت")
    await callback.message.edit_text(
        OrderService.admin_details_text(order),
        reply_markup=admin_order_details_keyboard(order.id),
    )


async def _answer_join_require_panel(callback: CallbackQuery, answer_text: str | None = None) -> None:
    if callback.message:
        await callback.message.edit_text(await _join_require_text(), reply_markup=join_require_keyboard())
    await callback.answer(answer_text)


async def _answer_plan_management_panel(callback: CallbackQuery, service_id: int, answer_text: str | None = None) -> None:
    service = await ServiceService.get_service(service_id)
    if service is None:
        await callback.answer("سرویس پیدا نشد", show_alert=True)
        return
    plan_count = await PlanService.count_plans(service_id)
    if callback.message:
        await callback.message.edit_text(_plan_management_text(service.name, plan_count), reply_markup=plan_management_keyboard(service_id))
    await callback.answer(answer_text)


async def _answer_financial_management_panel(callback: CallbackQuery, answer_text: str | None = None) -> None:
    if callback.message:
        await callback.message.edit_text(_financial_management_text(), reply_markup=financial_management_keyboard())
    await callback.answer(answer_text)


async def _answer_discount_codes_panel(callback: CallbackQuery, answer_text: str | None = None) -> None:
    if callback.message:
        await callback.message.edit_text(_discount_codes_text(), reply_markup=discount_codes_keyboard())
    await callback.answer(answer_text)


async def _join_require_text() -> str:
    channels = await RequiredChannelService.list_channels()
    if not channels:
        return "جوین اجباری\n\nکانالی ثبت نشده است."
    lines = ["جوین اجباری", "", "کانال‌های فعلی:"]
    lines.extend(f"- {escape(RequiredChannelService.get_channel_title(channel))}" for channel in channels)
    return "\n".join(lines)


async def _service_management_text() -> str:
    services = await ServiceService.list_services()
    return f"مدیریت سرویس‌ها\n\nتعداد سرویس‌ها: {len(services)}"


async def _service_list_text() -> str:
    services = await ServiceService.list_services()
    if not services:
        return "لیست سرویس‌ها\n\nهیچ سرویسی ثبت نشده است."
    lines = ["لیست سرویس‌ها", ""]
    lines.extend(f"- {escape(service.name)}" for service in services)
    return "\n".join(lines)


def _plan_management_text(service_name: str, plan_count: int) -> str:
    return f"مدیریت پلن\n\nنام سرویس: {escape(service_name)}\nتعداد پلن‌ها: {plan_count}"


def _financial_management_text() -> str:
    return "مدیریت مالی"


async def _card_list_text() -> str:
    cards = await BankCardService.list_cards()
    if not cards:
        return "Card List\n\nهیچ کارتی ثبت نشده است."
    lines = ["Card List", ""]
    for card in cards:
        lines.extend([escape(card.card_number), escape(card.owner_name), "", "---", ""])
    return "\n".join(lines).strip()


def _discount_codes_text() -> str:
    return "مدیریت کد تخفیف"


async def _discount_list_text() -> str:
    discounts = await DiscountCodeService.list_discounts()
    if not discounts:
        return "لیست کد های تخفیف\n\nهیچ کد تخفیفی ثبت نشده است."
    blocks: list[str] = []
    for discount in discounts:
        user_ids = "\n".join(str(usage.user_id) for usage in discount.usages) or "-"
        blocks.append(
            "کد:\n"
            f"{escape(discount.code)}\n\n"
            "تخفیف:\n"
            f"{discount.discount_amount} تومان\n\n"
            "استفاده:\n"
            f"{discount.used_count} / {discount.usage_limit}\n\n"
            "Users:\n\n"
            f"{user_ids}"
        )
    return "\n\n---\n\n".join(blocks)


def _parse_callback_int(callback_data: str | None) -> int | None:
    if not callback_data:
        return None
    value = callback_data.rsplit(":", maxsplit=1)[-1]
    if not value.isdigit():
        return None
    return int(value)
