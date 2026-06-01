import asyncio
import logging
import sys
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import settings
from bot.database import init_db
from bot.handlers import setup_routers
from bot.middlewares.join_required import JoinRequiredMiddleware


async def on_startup(**_: Any) -> None:
    await init_db()


async def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()

    dispatcher.startup.register(on_startup)
    dispatcher.message.middleware(JoinRequiredMiddleware())
    dispatcher.callback_query.middleware(JoinRequiredMiddleware())
    dispatcher.include_router(setup_routers())

    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
