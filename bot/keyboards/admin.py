from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.models import BankCard, DiscountCode, Order, Plan, RequiredChannel, Service
from bot.services.bank_card_service import BankCardService
from bot.services.order_service import OrderPage, OrderService
from bot.services.required_channel_service import RequiredChannelService


class AdminCallback:
    join_require = "admin:join_require"
    orders = "admin:orders"
    add_service = "admin:add_service"
    add_plan = "admin:add_plan"
    financial_management = "admin:financial"
    discount_codes = "admin:discounts"
    back = "admin:back"
    add_channel = "admin:join:add"
    delete_channel_menu = "admin:join:delete_menu"
    join_back = "admin:join:back"
    service_add = "admin:service:add"
    service_delete_menu = "admin:service:delete_menu"
    service_list = "admin:service:list"
    service_back = "admin:service:back"
    plans_back = "admin:plans:back"
    card_add = "admin:cards:add"
    card_delete_menu = "admin:cards:delete_menu"
    card_list = "admin:cards:list"
    card_back = "admin:cards:back"
    discount_create = "admin:discounts:create"
    discount_list = "admin:discounts:list"
    discount_delete_menu = "admin:discounts:delete_menu"
    discount_back = "admin:discounts:back"
    orders_back = "admin:orders:back"
    orders_search = "orders:search"


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="جوین اجباری", callback_data=AdminCallback.join_require))
    builder.row(
        InlineKeyboardButton(text="سفارش‌ها", callback_data=AdminCallback.orders),
        InlineKeyboardButton(text="مدیریت سرویس‌ها", callback_data=AdminCallback.add_service),
    )
    builder.row(InlineKeyboardButton(text="مدیریت پلن‌ها", callback_data=AdminCallback.add_plan))
    builder.row(InlineKeyboardButton(text="مدیریت مالی", callback_data=AdminCallback.financial_management))
    builder.row(InlineKeyboardButton(text="مدیریت کد تخفیف", callback_data=AdminCallback.discount_codes))
    builder.row(InlineKeyboardButton(text="بازگشت", callback_data=AdminCallback.back))
    return builder.as_markup()


def join_require_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="افزودن کانال", callback_data=AdminCallback.add_channel))
    builder.row(InlineKeyboardButton(text="حذف کانال", callback_data=AdminCallback.delete_channel_menu))
    builder.row(InlineKeyboardButton(text="بازگشت", callback_data=AdminCallback.join_back))
    return builder.as_markup()


def delete_channels_keyboard(channels: list[RequiredChannel]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for channel in channels:
        title = RequiredChannelService.get_channel_title(channel)
        builder.row(InlineKeyboardButton(text=f"حذف {title}", callback_data=f"admin:join:delete:{channel.channel_id}"))
    builder.row(InlineKeyboardButton(text="بازگشت", callback_data=AdminCallback.join_require))
    return builder.as_markup()


def service_management_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ افزودن سرویس", callback_data=AdminCallback.service_add))
    builder.row(InlineKeyboardButton(text="حذف سرویس", callback_data=AdminCallback.service_delete_menu))
    builder.row(InlineKeyboardButton(text="لیست سرویس‌ها", callback_data=AdminCallback.service_list))
    builder.row(InlineKeyboardButton(text="بازگشت", callback_data=AdminCallback.service_back))
    return builder.as_markup()


def delete_services_keyboard(services: list[Service]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for service in services:
        builder.row(InlineKeyboardButton(text=f"❌ {service.name}", callback_data=f"admin:service:delete:{service.id}"))
    builder.row(InlineKeyboardButton(text="بازگشت", callback_data=AdminCallback.add_service))
    return builder.as_markup()


def plan_services_keyboard(services: list[Service]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for service in services:
        builder.row(InlineKeyboardButton(text=service.name, callback_data=f"admin:plans:service:{service.id}"))
    builder.row(InlineKeyboardButton(text="بازگشت", callback_data=AdminCallback.plans_back))
    return builder.as_markup()


def plan_management_keyboard(service_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ افزودن پلن", callback_data=f"admin:plans:add:{service_id}"))
    builder.row(InlineKeyboardButton(text="حذف پلن", callback_data=f"admin:plans:delete_menu:{service_id}"))
    builder.row(InlineKeyboardButton(text="بازگشت", callback_data=AdminCallback.add_plan))
    return builder.as_markup()


def delete_plans_keyboard(service_id: int, plans: list[Plan]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for plan in plans:
        builder.row(InlineKeyboardButton(text=f"❌ {plan.name}", callback_data=f"admin:plans:delete:{service_id}:{plan.id}"))
    builder.row(InlineKeyboardButton(text="بازگشت", callback_data=f"admin:plans:service:{service_id}"))
    return builder.as_markup()


def financial_management_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ افزودن کارت", callback_data=AdminCallback.card_add))
    builder.row(InlineKeyboardButton(text="حذف کارت", callback_data=AdminCallback.card_delete_menu))
    builder.row(InlineKeyboardButton(text="لیست کارت‌ها", callback_data=AdminCallback.card_list))
    builder.row(InlineKeyboardButton(text="بازگشت", callback_data=AdminCallback.card_back))
    return builder.as_markup()


def delete_cards_keyboard(cards: list[BankCard]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for card in cards:
        builder.row(
            InlineKeyboardButton(
                text=f"❌ {BankCardService.mask_card_number(card.card_number)}",
                callback_data=f"admin:cards:delete:{card.id}",
            )
        )
    builder.row(InlineKeyboardButton(text="بازگشت", callback_data=AdminCallback.financial_management))
    return builder.as_markup()


def discount_codes_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ افزودن کد تخفیف", callback_data=AdminCallback.discount_create))
    builder.row(InlineKeyboardButton(text="لیست کدهای تخفیف", callback_data=AdminCallback.discount_list))
    builder.row(InlineKeyboardButton(text="حذف کد تخفیف", callback_data=AdminCallback.discount_delete_menu))
    builder.row(InlineKeyboardButton(text="بازگشت", callback_data=AdminCallback.discount_back))
    return builder.as_markup()


def delete_discounts_keyboard(discounts: list[DiscountCode]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for discount in discounts:
        builder.row(
            InlineKeyboardButton(
                text=f"❌ {discount.code}",
                callback_data=f"admin:discounts:delete:{discount.id}",
            )
        )
    builder.row(InlineKeyboardButton(text="بازگشت", callback_data=AdminCallback.discount_codes))
    return builder.as_markup()


def admin_orders_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="همه سفارش‌ها", callback_data="orders:all:page:1"))
    builder.row(InlineKeyboardButton(text="✅ سفارش‌های تایید شده", callback_data="orders:approved:page:1"))
    builder.row(InlineKeyboardButton(text="⏳ سفارش‌های درحال پیگیری", callback_data="orders:pending:page:1"))
    builder.row(InlineKeyboardButton(text="❌ سفارش‌های رد شده", callback_data="orders:rejected:page:1"))
    builder.row(InlineKeyboardButton(text="جستجوی سفارش", callback_data=AdminCallback.orders_search))
    builder.row(InlineKeyboardButton(text="بازگشت", callback_data=AdminCallback.orders_back))
    return builder.as_markup()


def admin_orders_keyboard(order_page: OrderPage, order_filter: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for order in order_page.orders:
       builder.row(
           InlineKeyboardButton(
               text=f"#{order.id} | {order.user_id}",
               callback_data=f"orders:view:{order_filter}:{order_page.page}:{order.id}",
           )
       )

    navigation_buttons: list[InlineKeyboardButton] = []
    if order_page.page > 1:
        navigation_buttons.append(
            InlineKeyboardButton(text="⬅️ صفحه قبل", callback_data=f"orders:{order_filter}:page:{order_page.page - 1}")
        )
    if order_page.page < order_page.page_count:
        navigation_buttons.append(
            InlineKeyboardButton(text="➡️ صفحه بعد", callback_data=f"orders:{order_filter}:page:{order_page.page + 1}")
        )
    if navigation_buttons:
        builder.row(*navigation_buttons)

    builder.row(InlineKeyboardButton(text="بازگشت", callback_data=AdminCallback.orders))
    return builder.as_markup()


def admin_order_details_keyboard(
    order_id: int,
    status: str,
    back_callback: str = "orders:all:page:1",
) -> InlineKeyboardMarkup:

    builder = InlineKeyboardBuilder()

    if status == "pending":
        builder.row(
            InlineKeyboardButton(
                text="✅ تایید سفارش",
                callback_data=f"admin:orders:approve:{order_id}",
            )
        )

        builder.row(
            InlineKeyboardButton(
                text="❌ رد سفارش",
                callback_data=f"admin:orders:reject:{order_id}",
            )
        )

    builder.row(
        InlineKeyboardButton(
            text="بازگشت",
            callback_data=back_callback,
        )
    )

    return builder.as_markup()


def admin_order_notification_keyboard(order_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="مشاهده سفارش", callback_data=f"admin:orders:view:{order_id}"))
    return builder.as_markup()
def _parse_order_view_callback(
    callback_data: str | None,
) -> tuple[str | None, int | None, int | None]:
    if not callback_data:
        return None, None, None

    parts = callback_data.split(":")

    if len(parts) != 5:
        return None, None, None

    if parts[0] != "orders" or parts[1] != "view":
        return None, None, None

    order_filter = parts[2]

    if not parts[3].isdigit() or not parts[4].isdigit():
        return None, None, None

    page = int(parts[3])
    order_id = int(parts[4])

    return order_filter, page, order_id