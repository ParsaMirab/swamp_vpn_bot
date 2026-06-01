import unittest
from dataclasses import dataclass

from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest

from bot.database.models import RequiredChannel
from bot.services.required_channel_service import RequiredChannelService


@dataclass(slots=True)
class FakeMember:
    status: ChatMemberStatus
    is_member: bool = False


class FakeBot:
    def __init__(self, responses: dict[int | str, FakeMember | Exception]) -> None:
        self.responses = responses
        self.calls: list[tuple[int | str, int]] = []

    async def get_chat_member(self, chat_id: int | str, user_id: int) -> FakeMember:
        self.calls.append((chat_id, user_id))
        response = self.responses[chat_id]
        if isinstance(response, Exception):
            raise response
        return response


class RequiredChannelServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_user_not_joined_is_rejected(self) -> None:
        channels = [RequiredChannel(channel_id=-1001, channel_username="channel_one")]
        bot = FakeBot({-1001: FakeMember(ChatMemberStatus.LEFT)})

        result = await RequiredChannelService.is_user_joined_all_required_channels(
            bot=bot,
            user_id=123,
            channels=channels,
        )

        self.assertFalse(result)

    async def test_user_joined_all_channels_is_accepted(self) -> None:
        channels = [
            RequiredChannel(channel_id=-1001, channel_username="channel_one"),
            RequiredChannel(channel_id=-1002, channel_username="channel_two"),
        ]
        bot = FakeBot(
            {
                -1001: FakeMember(ChatMemberStatus.MEMBER),
                -1002: FakeMember(ChatMemberStatus.ADMINISTRATOR),
            }
        )

        result = await RequiredChannelService.is_user_joined_all_required_channels(
            bot=bot,
            user_id=123,
            channels=channels,
        )

        self.assertTrue(result)

    async def test_channel_username_is_used_as_fallback(self) -> None:
        channels = [RequiredChannel(channel_id=-1001, channel_username="channel_one")]
        bot = FakeBot(
            {
                -1001: TelegramBadRequest(method=None, message="chat not found"),
                "@channel_one": FakeMember(ChatMemberStatus.MEMBER),
            }
        )

        result = await RequiredChannelService.is_user_joined_all_required_channels(
            bot=bot,
            user_id=123,
            channels=channels,
        )

        self.assertTrue(result)
        self.assertEqual(bot.calls, [(-1001, 123), ("@channel_one", 123)])

    async def test_member_list_inaccessible_is_reported_when_adding_channel(self) -> None:
        bot = FakeBot(
            {
                -1001: TelegramBadRequest(method=None, message="member list is inaccessible"),
                "@channel_one": TelegramBadRequest(method=None, message="member list is inaccessible"),
            }
        )

        with self.assertRaisesRegex(ValueError, "لیست اعضای این کانال"):
            await RequiredChannelService.ensure_membership_check_available(
                bot=bot,
                channel_id=-1001,
                channel_username="channel_one",
                probe_user_id=123,
            )


if __name__ == "__main__":
    unittest.main()
