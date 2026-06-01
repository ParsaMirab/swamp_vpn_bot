from dataclasses import dataclass
from collections.abc import Sequence
import logging

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlalchemy import delete, select

from bot.database.base import async_session_factory
from bot.database.models import RequiredChannel


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ChannelInput:
    channel_id: int
    channel_username: str | None


class RequiredChannelService:
    allowed_member_statuses = {
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.CREATOR,
    }

    @staticmethod
    async def list_channels() -> list[RequiredChannel]:
        async with async_session_factory() as session:
            result = await session.execute(
                select(RequiredChannel).order_by(RequiredChannel.id.asc())
            )
            return list(result.scalars().all())

    @staticmethod
    async def add_channel(channel_id: int, channel_username: str | None) -> RequiredChannel:
        normalized_username = RequiredChannelService.normalize_username(channel_username)

        async with async_session_factory() as session:
            result = await session.execute(
                select(RequiredChannel).where(RequiredChannel.channel_id == channel_id)
            )
            channel = result.scalar_one_or_none()

            if channel is None:
                channel = RequiredChannel(
                    channel_id=channel_id,
                    channel_username=normalized_username,
                )
                session.add(channel)
            else:
                channel.channel_username = normalized_username

            await session.commit()
            await session.refresh(channel)
            return channel

    @staticmethod
    async def delete_channel(channel_id: int) -> bool:
        async with async_session_factory() as session:
            result = await session.execute(
                delete(RequiredChannel).where(RequiredChannel.channel_id == channel_id)
            )
            await session.commit()
            return bool(result.rowcount)

    @staticmethod
    async def is_user_joined_all_required_channels(
        bot: Bot,
        user_id: int,
        channels: Sequence[RequiredChannel] | None = None,
    ) -> bool:
        if channels is None:
            channels = await RequiredChannelService.list_channels()
        if not channels:
            return True

        for channel in channels:
            chat_ids: list[int | str] = [channel.channel_id]
            if channel.channel_username:
                chat_ids.append(f"@{channel.channel_username}")

            member = None
            last_error: Exception | None = None
            for chat_id in chat_ids:
                try:
                    member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
                    break
                except (TelegramBadRequest, TelegramForbiddenError) as exc:
                    last_error = exc
                    continue

            if member is None:
                logger.warning(
                    "Failed to check membership for all channel identifiers: channel_id=%s username=%s user_id=%s error=%s",
                    channel.channel_id,
                    channel.channel_username,
                    user_id,
                    last_error,
                )
                return False

            if member.status in RequiredChannelService.allowed_member_statuses:
                continue
            if member.status == ChatMemberStatus.RESTRICTED and getattr(member, "is_member", False):
                continue
            return False

        return True

    @staticmethod
    async def resolve_channel(bot: Bot, raw_channel: str) -> ChannelInput:
        chat_identifier = RequiredChannelService.normalize_chat_identifier(raw_channel)
        try:
            chat = await bot.get_chat(chat_identifier)
        except (TelegramBadRequest, TelegramForbiddenError) as exc:
            raise ValueError(
                "کانال پیدا نشد یا ربات به آن دسترسی ندارد. ربات را داخل کانال اضافه کنید و دوباره تلاش کنید."
            ) from exc

        return ChannelInput(
            channel_id=chat.id,
            channel_username=RequiredChannelService.normalize_username(chat.username),
        )

    @staticmethod
    async def ensure_membership_check_available(
        bot: Bot,
        channel_id: int,
        channel_username: str | None,
        probe_user_id: int,
    ) -> None:
        chat_ids: list[int | str] = [channel_id]
        if channel_username:
            chat_ids.append(f"@{channel_username}")

        last_error: Exception | None = None
        for chat_id in chat_ids:
            try:
                await bot.get_chat_member(chat_id=chat_id, user_id=probe_user_id)
                return
            except TelegramBadRequest as exc:
                last_error = exc
                if "member list is inaccessible" in str(exc).lower():
                    raise ValueError(
                        "ربات به لیست اعضای این کانال دسترسی ندارد. ربات را در کانال ادمین کنید و دوباره کانال را ثبت کنید."
                    ) from exc
            except TelegramForbiddenError as exc:
                last_error = exc

        raise ValueError(
            "امکان بررسی عضویت این کانال وجود ندارد. ربات را داخل کانال اضافه و ادمین کنید."
        ) from last_error

    @staticmethod
    def normalize_chat_identifier(raw_channel: str) -> str | int:
        value = raw_channel.strip()
        if not value:
            raise ValueError("شناسه یا username کانال را ارسال کنید.")

        if value.startswith("https://t.me/"):
            value = value.removeprefix("https://t.me/").strip("/")

        if value.startswith("@"):
            value = value[1:]

        if value.lstrip("-").isdigit():
            return int(value)

        return f"@{value}"

    @staticmethod
    def normalize_username(username: str | None) -> str | None:
        if not username:
            return None
        return username.strip().lstrip("@") or None

    @staticmethod
    def get_channel_title(channel: RequiredChannel) -> str:
        if channel.channel_username:
            return f"@{channel.channel_username}"
        return str(channel.channel_id)

    @staticmethod
    def get_channel_url(channel: RequiredChannel) -> str:
        if channel.channel_username:
            return f"https://t.me/{channel.channel_username}"

        channel_id = str(channel.channel_id)
        if channel_id.startswith("-100") and len(channel_id) > 4:
            return f"https://t.me/c/{channel_id[4:]}"
        return "https://t.me/"
