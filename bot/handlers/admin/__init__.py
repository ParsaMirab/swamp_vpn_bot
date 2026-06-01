from aiogram import Router

from bot.handlers.admin.panel import router as panel_router

router = Router(name="admin")
router.include_router(panel_router)
