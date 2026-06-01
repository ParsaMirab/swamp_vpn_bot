import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from aiogram.types import CallbackQuery, Chat, Message, User

from bot.handlers.user.start import join_required_check
from bot.keyboards.join_required import JOIN_REQUIRED_CHECK_CALLBACK


class JoinRequiredCallbackTest(unittest.IsolatedAsyncioTestCase):
    def _make_callback(self) -> CallbackQuery:
        return CallbackQuery(
            id="callback-id",
            from_user=User(id=123, is_bot=False, first_name="Test"),
            chat_instance="chat-instance",
            data=JOIN_REQUIRED_CHECK_CALLBACK,
            message=Message(
                message_id=1,
                date=datetime.now(timezone.utc),
                chat=Chat(id=123, type="private"),
                text="برای استفاده از ربات ابتدا در کانال‌های زیر عضو شوید.",
            ),
        )

    async def test_joined_user_gets_access_after_clicking_joined_button(self) -> None:
        callback = self._make_callback()
        bot = AsyncMock()
        answer_mock = AsyncMock()
        edit_text_mock = AsyncMock()

        with patch(
            "bot.handlers.user.start.RequiredChannelService.is_user_joined_all_required_channels",
            AsyncMock(return_value=True),
        ), patch.object(CallbackQuery, "answer", answer_mock), patch.object(
            Message, "edit_text", edit_text_mock
        ):
            await join_required_check(callback, bot)

        answer_mock.assert_awaited_once_with("عضویت شما تایید شد.")
        edit_text_mock.assert_awaited_once()

    async def test_not_joined_user_stays_on_join_required_message(self) -> None:
        callback = self._make_callback()
        bot = AsyncMock()
        answer_mock = AsyncMock()
        edit_text_mock = AsyncMock()

        with patch(
            "bot.handlers.user.start.RequiredChannelService.is_user_joined_all_required_channels",
            AsyncMock(return_value=False),
        ), patch(
            "bot.handlers.user.start.RequiredChannelService.list_channels",
            AsyncMock(return_value=[]),
        ), patch.object(CallbackQuery, "answer", answer_mock), patch.object(
            Message, "edit_text", edit_text_mock
        ):
            await join_required_check(callback, bot)

        answer_mock.assert_awaited_once_with("هنوز عضو همه کانال‌ها نشده‌اید.", show_alert=True)
        edit_text_mock.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
