import asyncio
import logging
from html import escape
from pathlib import Path

logger = logging.getLogger(__name__)

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.types import FSInputFile

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
    wallet_keyboard,
    recharge_packages_keyboard,
    wallet_transactions_keyboard,
)
from bot.config import settings
from bot.keyboards.admin import wallet_notification_keyboard, card_to_card_notification_keyboard
from bot.services.discount_service import DiscountCodeService
from bot.services.order_service import OrderService
from bot.services.plan_service import PlanService
from bot.services.required_channel_service import RequiredChannelService
from bot.services.service_service import ServiceService
from bot.services.setting_service import SettingService
from bot.services.wallet_service import WalletService
from bot.services.sanaei_service import SanaeiService
from bot.services.bank_card_service import BankCardService
from bot.states.user import UserOrderStates, UserWalletStates, UserCardToCardStates
from bot.services.user_service import UserService

router = Router(name="user_start")
ASSETS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "assets"
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
    orders.reverse()
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


@router.callback_query(F.data == UserCallback.my_wallet)
async def user_wallet(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if not callback.from_user:
        await callback.answer()
        return
    balance = await WalletService.get_balance(callback.from_user.id)
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(
            f"💰 کیف پول شما\n\nموجودی: {balance:,} تومان",
            reply_markup=wallet_keyboard(balance),
        )


@router.callback_query(F.data == UserCallback.wallet_recharge)
async def user_wallet_recharge(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    packages = await WalletService.list_active_packages()
    await callback.answer()
    if not callback.message:
        return
    if not packages:
        await callback.message.edit_text(
            "هیچ پکیج شارژی فعال نیست.",
            reply_markup=wallet_keyboard(await WalletService.get_balance(callback.from_user.id) if callback.from_user else 0),
        )
        return
    await callback.message.edit_text(
        "پکیج شارژ موردنظر را انتخاب کنید.",
        reply_markup=recharge_packages_keyboard(packages),
    )


@router.callback_query(F.data.startswith("user:wallet:recharge:select:"))
async def select_recharge_package(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    package_id = _parse_callback_int(callback.data)
    if package_id is None:
        await callback.answer()
        return
    package = await WalletService.get_package(package_id)
    if package is None:
        await callback.answer("پکیج پیدا نشد", show_alert=True)
        return
    await state.update_data(package_id=package_id, package_amount=package.amount)
    await state.set_state(UserWalletStates.waiting_for_receipt)
    await callback.answer()
    card = await BankCardService.get_first_card()
    if callback.message:
        text = (
            f"💰 شارژ کیف پول\n\n"
            f"مبلغ: {package.amount:,} تومان\n\n"
        )
        if card:
            text += (
                f"💳 کارت بانکی:\n"
                f"<code>{escape(card.card_number)}</code>\n"
                f"👤 {escape(card.owner_name)}\n\n"
            )
        text += "📸 تصویر فیش واریزی را ارسال کنید."
        await callback.message.answer(text)


@router.message(UserWalletStates.waiting_for_receipt)
async def wallet_receipt_upload(message: Message, state: FSMContext, bot: Bot) -> None:
    if not message.from_user:
        await state.clear()
        await message.answer("خطا در پردازش درخواست.")
        return
    data = await state.get_data()
    package_id = data.get("package_id")
    package_amount = data.get("package_amount")
    if not isinstance(package_id, int) or not isinstance(package_amount, int):
        await state.clear()
        await message.answer("پکیج شارژ معتبر نیست.")
        return
    if not message.photo:
        await message.answer("لطفاً تصویر فیش واریزی را ارسال نمایید.")
        return
    receipt_file_id = message.photo[-1].file_id
    try:
        transaction = await WalletService.create_credit_transaction(
            user_id=message.from_user.id,
            amount=package_amount,
            description=f"شارژ کیف پول - پکیج {package_id}",
            receipt_file_id=receipt_file_id,
        )
    except Exception as e:
        await state.clear()
        await message.answer(f"خطا در ثبت درخواست: {e}")
        return
    await state.clear()
    try:
        await bot.send_message(
            chat_id=settings.admin_id,
            text=await WalletService.admin_notification_text(transaction),
            reply_markup=wallet_notification_keyboard(transaction.id),
        )
    except TelegramAPIError:
        pass
    await message.answer("✅ درخواست شارژ کیف پول شما ثبت شد.\n\n⏳ در انتظار بررسی توسط ادمین.")


@router.callback_query(F.data == UserCallback.wallet_transactions)
async def user_wallet_transactions(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if not callback.from_user:
        await callback.answer()
        return
    transactions = await WalletService.list_user_transactions(callback.from_user.id)
    await callback.answer()
    if not callback.message:
        return
    if not transactions:
        await callback.message.edit_text(
            "تاریخچه تراکنش‌ها\n\nهنوز تراکنشی ثبت نشده است.",
            reply_markup=wallet_keyboard(await WalletService.get_balance(callback.from_user.id)),
        )
        return
    await callback.message.edit_text(
        "تاریخچه تراکنش‌ها",
        reply_markup=wallet_transactions_keyboard(transactions),
    )


@router.callback_query(F.data == UserCallback.wallet_back)
async def user_wallet_back(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if callback.message:
        await callback.message.edit_text(WELCOME_TEXT, reply_markup=main_menu_keyboard())


@router.callback_query(F.data == UserCallback.pay_with_wallet)
async def pay_with_wallet(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    data = await state.get_data()
    service_id = data.get("service_id")
    plan_id = data.get("plan_id")
    final_price = data.get("final_price")
    discount_id = data.get("discount_id")
    if not isinstance(service_id, int) or not isinstance(plan_id, int) or not isinstance(final_price, int):
        await callback.answer("ابتدا یک پلن انتخاب کنید.", show_alert=True)
        return
    if final_price <= 0:
        await callback.answer("مبلغ نهایی نامعتبر است.", show_alert=True)
        return
    has_balance = await WalletService.has_sufficient_balance(callback.from_user.id, final_price)
    if not has_balance:
        await callback.answer("موجودی کیف پول کافی نیست.", show_alert=True)
        return
    plan = await PlanService.get_plan(plan_id=plan_id, service_id=service_id)
    if plan is None:
        await callback.answer("پلن پیدا نشد", show_alert=True)
        return
    if not plan.inbound_id:
        await callback.answer("تنظیمات پلن ناقص است. با پشتیبانی تماس بگیرید.", show_alert=True)
        return
    await callback.answer()
    status_msg = await callback.message.answer("⏳ در حال پردازش خرید...")
    order = None
    deducted = False
    try:
        await WalletService.deduct_balance(
            user_id=callback.from_user.id,
            amount=final_price,
            description=f"خرید سرویس {plan.service.name} - پلن {plan.name}",
        )
        deducted = True
        order = await OrderService.create_wallet_order(
            user_id=callback.from_user.id,
            service_id=service_id,
            plan_id=plan_id,
            original_price=plan.price,
            final_price=final_price,
            discount_id=discount_id if isinstance(discount_id, int) else None,
        )
        sanaei = SanaeiService(
            api_key=settings.sanaei_api_key,
            base_url=settings.sanaei_base_url,
            sub_url=settings.sanaei_sub_url,
        )
        result = await sanaei.create_user(
            inbound_id=plan.inbound_id,
            traffic_gb=plan.traffic_limit_gb,
            duration_days=plan.duration_days,
            limit_ip=plan.limit_ip,
        )
        await asyncio.sleep(5)
        links = await sanaei.get_config(result["email"])
        sub_link = "\n".join(links) if links else ""
        logger.info("create_user result: email=%s, sub_id=%s", result["email"], result["sub_id"])
        sub_url = sanaei.get_sub_url(result["sub_id"])
        logger.info("sub_url: %s", sub_url)
        config_text = sub_url
        await OrderService.complete_order(order.id, sub_link=sub_link, config_text=config_text)
        await status_msg.delete()
        link_text = "\n".join(links[:3]) if links else "ندارد"
        caption = (
            f"✅ خرید شما با موفقیت انجام شد.\n\n"
            f"🔗 لینک اشتراک:\n<code>{escape(sub_url)}</code>\n\n"
            f"⚙️ کانفیگ‌ها:\n<code>{escape(link_text)}</code>\n\n"
            f"💾 از بخش «سفارش‌های من» می‌توانید در هر زمان مجدداً اطلاعات سرویس خود را مشاهده کنید."
        )
        photo_path = ASSETS_DIR / "order_approved.jpg"
        if photo_path.exists():
            photo = FSInputFile(photo_path)
            await bot.send_photo(
                chat_id=callback.from_user.id,
                photo=photo,
                caption=caption,
            )
        else:
            await callback.message.answer(caption)
    except Exception as e:
        if deducted:
            try:
                await WalletService.refund_balance(
                    user_id=callback.from_user.id,
                    amount=final_price,
                    description=f"بازگشت وجه خرید ناموفق",
                )
            except Exception:
                pass
        if order is not None:
            try:
                await OrderService.fail_order(order.id)
            except Exception:
                pass
        await status_msg.delete()
        await callback.message.answer(
            f"❌ خطا در پردازش خرید.\n\n"
            f"خطا: {escape(str(e))}\n\n"
            "وجه به کیف پول شما بازگردانده شد.\n"
            "در صورت تکرار مشکل با پشتیبانی تماس بگیرید."
        )


@router.callback_query(F.data == UserCallback.pay_card_to_card)
async def pay_card_to_card_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user:
        await callback.answer()
        return
    data = await state.get_data()
    service_id = data.get("service_id")
    plan_id = data.get("plan_id")
    final_price = data.get("final_price")
    discount_id = data.get("discount_id")
    if not isinstance(service_id, int) or not isinstance(plan_id, int) or not isinstance(final_price, int):
        await callback.answer("ابتدا یک پلن انتخاب کنید.", show_alert=True)
        return
    if final_price <= 0:
        await callback.answer("مبلغ نهایی نامعتبر است.", show_alert=True)
        return
    plan = await PlanService.get_plan(plan_id=plan_id, service_id=service_id)
    if plan is None:
        await callback.answer("پلن پیدا نشد", show_alert=True)
        return

    await state.update_data(
        service_id=service_id,
        plan_id=plan_id,
        final_price=final_price,
        discount_id=discount_id,
    )
    await state.set_state(UserCardToCardStates.waiting_for_receipt)
    await callback.answer()
    card = await BankCardService.get_first_card()
    if callback.message:
        text = (
            f"💳 پرداخت کارت به کارت\n\n"
            f"مبلغ قابل پرداخت: {final_price:,} تومان\n\n"
        )
        if card:
            text += (
                f"💳 کارت بانکی:\n"
                f"<code>{escape(card.card_number)}</code>\n"
                f"👤 {escape(card.owner_name)}\n\n"
            )
        else:
            text += "⚠️ هیچ کارت بانکی ثبت نشده است.\n\n"
        text += "📸 تصویر فیش واریزی را ارسال کنید."
        await callback.message.answer(text)


@router.message(UserCardToCardStates.waiting_for_receipt)
async def card_to_card_receipt_upload(message: Message, state: FSMContext, bot: Bot) -> None:
    if not message.from_user:
        await state.clear()
        await message.answer("خطا در پردازش درخواست.")
        return
    data = await state.get_data()
    service_id = data.get("service_id")
    plan_id = data.get("plan_id")
    final_price = data.get("final_price")
    discount_id = data.get("discount_id")
    if not isinstance(service_id, int) or not isinstance(plan_id, int) or not isinstance(final_price, int):
        await state.clear()
        await message.answer("اطلاعات سفارش معتبر نیست.")
        return
    if not message.photo:
        await message.answer("لطفاً تصویر فیش واریزی را ارسال نمایید.")
        return
    receipt_file_id = message.photo[-1].file_id
    try:
        order = await OrderService.create_order(
            user_id=message.from_user.id,
            service_id=service_id,
            plan_id=plan_id,
            original_price=final_price,
            final_price=final_price,
            discount_id=discount_id if isinstance(discount_id, int) else None,
            receipt_file_id=receipt_file_id,
            payment_type="card_to_card",
        )
    except Exception as e:
        await state.clear()
        await message.answer(f"خطا در ثبت سفارش: {e}")
        return
    await state.clear()

    plan = await PlanService.get_plan(plan_id=plan_id, service_id=service_id)
    plan_name = plan.name if plan else "نامشخص"

    try:
        await bot.send_message(
            chat_id=settings.admin_id,
            text=(
                f"💳 سفارش جدید کارت به کارت\n\n"
                f"کاربر:\n{message.from_user.id}\n\n"
                f"سرویس:\n{plan.service.name if plan and plan.service else 'نامشخص'}\n\n"
                f"پلن:\n{escape(plan_name)}\n\n"
                f"مبلغ:\n{final_price:,} تومان\n\n"
                f"شماره سفارش:\n{order.id}"
            ),
            reply_markup=card_to_card_notification_keyboard(order.id),
        )
    except TelegramAPIError:
        pass
    await message.answer(
        "✅ سفارش شما ثبت شد.\n\n"
        f"شماره سفارش: #{order.id}\n"
        "⏳ در انتظار بررسی توسط ادمین و ساخت اکانت."
    )
