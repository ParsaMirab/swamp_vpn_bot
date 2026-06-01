from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.models import RequiredChannel
from bot.services.required_channel_service import RequiredChannelService


JOIN_REQUIRED_CHECK_CALLBACK = "join_required:check"


def join_required_keyboard(channels: list[RequiredChannel]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for channel in channels:
        title = RequiredChannelService.get_channel_title(channel)
        url = RequiredChannelService.get_channel_url(channel)
        builder.row(InlineKeyboardButton(text=title, url=url))

    builder.row(
        InlineKeyboardButton(
            text="✅ عضو شدم",
            callback_data=JOIN_REQUIRED_CHECK_CALLBACK,
        )
    )
    return builder.as_markup()
