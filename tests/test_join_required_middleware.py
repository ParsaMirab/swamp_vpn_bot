import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from aiogram.enums import ChatMemberStatus
from aiogram.types import CallbackQuery
from aiogram.types import Chat, Message, User

from bot.keyboards.join_required import JOIN_REQUIRED_CHECK_CALLBACK
from bot.database.models import RequiredChannel
from bot.middlewares.join_required import JoinRequiredMiddleware


class JoinRequiredMiddlewareTest(unittest.IsolatedAsyncioTestCase):
    async def test_not_joined_user_is_blocked_before_handler(self) -> None:
        channel = RequiredChannel(channel_id=-1001, channel_username="channel_one")
        event = Message(
            message_id=1,
            date=datetime.now(timezone.utc),
            chat=Chat(id=123, type="private"),
            from_user=User(id=123, is_bot=False, first_name="Test"),
            text="/start",
        )
        handler = AsyncMock()
        bot = AsyncMock()
        bot.get_chat_member.return_value.status = ChatMemberStatus.LEFT

        answer_mock = AsyncMock()
        with patch(
            "bot.middlewares.join_required.RequiredChannelService.list_channels",
            AsyncMock(return_value=[channel]),
        ), patch.object(Message, "answer", answer_mock):
            result = await JoinRequiredMiddleware()(handler, event, {"bot": bot})

        self.assertIsNone(result)
        handler.assert_not_awaited()
        answer_mock.assert_awaited_once()

    async def test_joined_user_reaches_handler(self) -> None:
        channel = RequiredChannel(channel_id=-1001, channel_username="channel_one")
        event = Message(
            message_id=1,
            date=datetime.now(timezone.utc),
            chat=Chat(id=123, type="private"),
            from_user=User(id=123, is_bot=False, first_name="Test"),
            text="/start",
        )
        handler = AsyncMock(return_value="handled")
        bot = AsyncMock()
        bot.get_chat_member.return_value.status = ChatMemberStatus.MEMBER

        with patch(
            "bot.middlewares.join_required.RequiredChannelService.list_channels",
            AsyncMock(return_value=[channel]),
        ):
            result = await JoinRequiredMiddleware()(handler, event, {"bot": bot})

        self.assertEqual(result, "handled")
        handler.assert_awaited_once()

    async def test_joined_button_callback_reaches_handler_without_middleware_block(self) -> None:
        event = CallbackQuery(
            id="callback-id",
            from_user=User(id=123, is_bot=False, first_name="Test"),
            chat_instance="chat-instance",
            data=JOIN_REQUIRED_CHECK_CALLBACK,
        )
        handler = AsyncMock(return_value="handled")
        bot = AsyncMock()

        result = await JoinRequiredMiddleware()(handler, event, {"bot": bot})

        self.assertEqual(result, "handled")
        handler.assert_awaited_once()
        bot.get_chat_member.assert_not_called()


if __name__ == "__main__":
    unittest.main()
