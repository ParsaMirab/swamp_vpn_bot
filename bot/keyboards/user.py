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


def main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="خرید سرویس", callback_data=UserCallback.buy_service))
    builder.row(
        InlineKeyboardButton(text="سفارش‌های من", callback_data=UserCallback.my_services),
        InlineKeyboardButton(text="پشتیبانی", url="tg://resolve?domain=The1Rocky"),
    )
    return builder.as_markup()


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
    builder.row(InlineKeyboardButton(text="ثبت سفارش", callback_data=UserCallback.register_order))
    builder.row(InlineKeyboardButton(text="کد تخفیف", callback_data=UserCallback.enter_discount))
    builder.row(InlineKeyboardButton(text="بازگشت", callback_data=f"user:buy:service:{service_id}"))
    return builder.as_markup()


def user_orders_keyboard(orders: list[Order]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for order in orders:
        builder.row(
            InlineKeyboardButton(
                text=f"#{order.id} | {OrderService.status_label(order.status)}",
                callback_data=f"user:orders:view:{order.id}",
            )
        )
    builder.row(InlineKeyboardButton(text="بازگشت", callback_data=UserCallback.back_to_main))
    return builder.as_markup()


def user_order_details_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="بازگشت", callback_data=UserCallback.my_services))
    return builder.as_markup()
