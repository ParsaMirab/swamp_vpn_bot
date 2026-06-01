from aiogram import Router

from bot.handlers.admin import router as admin_router
from bot.handlers.user import router as user_router


def setup_routers() -> Router:
    router = Router()
    router.include_router(admin_router)
    router.include_router(user_router)
    return router
