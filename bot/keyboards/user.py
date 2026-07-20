from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.models import Order, Plan, Service
from bot.services.order_service import OrderService


class UserCallback:
    buy_service = "user:buy_service"
    my_services = "user:my_services"
    back_to_main = "user:back_to_main"
    register_order = "user:order:register"
    enter_discount = "user:order:discount"
    pay_with_wallet = "user:order:pay_wallet"
    pay_card_to_card = "user:order:pay_card_to_card"
    my_wallet = "user:wallet"
    wallet_recharge = "user:wallet:recharge"
    wallet_transactions = "user:wallet:transactions"
    wallet_back = "user:wallet:back"


def user_services_keyboard(services: list[Service]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for service in services:
        builder.row(InlineKeyboardButton(text=service.name, callback_data=f"user:buy:service:{service.id}"))
    builder.row(InlineKeyboardButton(text="بازگشت", callback_data=UserCallback.back_to_main))
    return builder.as_markup()


def user_plans_keyboard(service_id: int, plans: list[Plan]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for plan in plans:
        builder.row(InlineKeyboardButton(text=plan.name, callback_data=f"user:buy:plan:{service_id}:{plan.id}"))
    builder.row(InlineKeyboardButton(text="بازگشت", callback_data=UserCallback.buy_service))
    return builder.as_markup()


def plan_details_keyboard(service_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="پرداخت از کیف پول", callback_data=UserCallback.pay_with_wallet))
    builder.row(InlineKeyboardButton(text="پرداخت کارت به کارت", callback_data=UserCallback.pay_card_to_card))
    builder.row(InlineKeyboardButton(text="کد تخفیف", callback_data=UserCallback.enter_discount))
    builder.row(InlineKeyboardButton(text="بازگشت", callback_data=f"user:buy:service:{service_id}"))
    return builder.as_markup()


def user_orders_keyboard(orders: list[Order]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for order in orders:
        status_icon = {
            "pending": "⏳",
            "approved": "✅",
            "completed": "✅",
            "rejected": "❌",
            "failed": "❌",
        }.get(order.status, "")
        plan_name = order.plan.name if order.plan else "حذف شده"
        builder.row(
            InlineKeyboardButton(
                text=f"#{order.id} | {plan_name} | {order.final_price:,} تومان | {status_icon}",
                callback_data=f"user:orders:view:{order.id}",
            )
        )
    builder.row(InlineKeyboardButton(text="بازگشت", callback_data=UserCallback.back_to_main))
    return builder.as_markup()


def user_order_details_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="بازگشت", callback_data=UserCallback.my_services))
    return builder.as_markup()


def main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="خرید سرویس", callback_data=UserCallback.buy_service))
    builder.row(InlineKeyboardButton(text="کیف پول من", callback_data=UserCallback.my_wallet))
    builder.row(
        InlineKeyboardButton(text="سفارش‌های من", callback_data=UserCallback.my_services),
        InlineKeyboardButton(text="پشتیبانی", url="tg://resolve?domain=The1Rocky"),
    )
    return builder.as_markup()


def wallet_keyboard(balance: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=f"موجودی: {balance:,} تومان", callback_data="ignore"))
    builder.row(InlineKeyboardButton(text="شارژ کیف پول", callback_data=UserCallback.wallet_recharge))
    builder.row(InlineKeyboardButton(text="تاریخچه تراکنش‌ها", callback_data=UserCallback.wallet_transactions))
    builder.row(InlineKeyboardButton(text="بازگشت", callback_data=UserCallback.back_to_main))
    return builder.as_markup()


def recharge_packages_keyboard(packages: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for pkg in packages:
        builder.row(
            InlineKeyboardButton(
                text=f"{pkg.title} - {pkg.amount:,} تومان",
                callback_data=f"user:wallet:recharge:select:{pkg.id}",
            )
        )
    builder.row(InlineKeyboardButton(text="بازگشت", callback_data=UserCallback.my_wallet))
    return builder.as_markup()


def wallet_transactions_keyboard(transactions: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for tx in transactions[:10]:
        type_icon = "💰" if tx.transaction_type == "credit" else "💸"
        status_icon = {"pending": "⏳", "approved": "✅", "rejected": "❌"}.get(tx.status, "")
        builder.row(
            InlineKeyboardButton(
                text=f"{type_icon} #{tx.id} | {tx.amount:,} تومان | {status_icon}",
                callback_data="ignore",
            )
        )
    builder.row(InlineKeyboardButton(text="بازگشت", callback_data=UserCallback.my_wallet))
    return builder.as_markup()


def wallet_plan_details_keyboard(service_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="پرداخت از کیف پول", callback_data=UserCallback.pay_with_wallet))
    builder.row(InlineKeyboardButton(text="بازگشت", callback_data=f"user:buy:service:{service_id}"))
    return builder.as_markup()
