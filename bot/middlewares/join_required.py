from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message, TelegramObject, User

from bot.database.models import RequiredChannel
from bot.keyboards.join_required import JOIN_REQUIRED_CHECK_CALLBACK, join_required_keyboard
from bot.services.required_channel_service import RequiredChannelService


class JoinRequiredMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = self._get_user(event)
        if user is None or user.is_bot:
            return await handler(event, data)
        if self._is_admin_management_event(event, user.id, data):
            return await handler(event, data)
        if isinstance(event, CallbackQuery) and event.data == JOIN_REQUIRED_CHECK_CALLBACK:
            return await handler(event, data)

        bot: Bot = data["bot"]
        channels = await RequiredChannelService.list_channels()
        if not channels:
            return await handler(event, data)

        is_member = await RequiredChannelService.is_user_joined_all_required_channels(
            bot=bot,
            user_id=user.id,
            channels=channels,
        )
        if is_member:
            return await handler(event, data)

        await self._send_join_required_message(event, channels)
        return None

    @staticmethod
    def _get_user(event: TelegramObject) -> User | None:
        if isinstance(event, Message):
            return event.from_user
        if isinstance(event, CallbackQuery):
            return event.from_user
        return None

    @staticmethod
    def _is_admin_management_event(
        event: TelegramObject,
        user_id: int,
        data: dict[str, Any],
    ) -> bool:
        from bot.config import settings
        from bot.states.admin import JoinRequireStates, PlanStates, ServiceStates

        if user_id != settings.admin_id:
            return False
        admin_fsm_states = {
            JoinRequireStates.waiting_for_channel.state,
            ServiceStates.waiting_for_name.state,
            PlanStates.waiting_for_name.state,
        }
        if data.get("raw_state") in admin_fsm_states:
            return True
        if isinstance(event, Message) and event.text and event.text.startswith("/admin"):
            return True
        if isinstance(event, CallbackQuery) and event.data and event.data.startswith("admin:"):
            return True
        return False

    @staticmethod
    async def _send_join_required_message(
        event: TelegramObject,
        channels: list[RequiredChannel],
    ) -> None:
        text = "برای استفاده از ربات ابتدا در کانال‌های زیر عضو شوید."
        keyboard = join_required_keyboard(channels)

        if isinstance(event, CallbackQuery):
            await event.answer()
            if event.message:
                try:
                    await event.message.edit_text(text, reply_markup=keyboard)
                    return
                except TelegramBadRequest:
                    await event.message.answer(text, reply_markup=keyboard)
                    return

        if isinstance(event, Message):
            await event.answer(text, reply_markup=keyboard)
