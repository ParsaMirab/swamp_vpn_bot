from aiogram import Router

from bot.handlers.user.start import router as start_router

router = Router(name="user")
router.include_router(start_router)
