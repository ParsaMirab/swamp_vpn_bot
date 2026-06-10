from sqlalchemy import select, update

from bot.database.base import async_session_factory
from bot.database.models import Setting


class SettingService:
    @staticmethod
    async def get_setting(key: str, default: str = "") -> str:
        async with async_session_factory() as session:
            result = await session.execute(
                select(Setting).where(Setting.key == key)
            )
            setting = result.scalar_one_or_none()
            if setting is None:
                return default
            return setting.value

    @staticmethod
    async def set_setting(key: str, value: str) -> None:
        async with async_session_factory() as session:
            result = await session.execute(
                select(Setting).where(Setting.key == key)
            )
            setting = result.scalar_one_or_none()
            if setting is None:
                setting = Setting(key=key, value=value)
                session.add(setting)
            else:
                setting.value = value
            await session.commit()

    @staticmethod
    async def is_sales_open() -> bool:
        value = await SettingService.get_setting("sales_open", "true")
        return value == "true"

    @staticmethod
    async def toggle_sales() -> bool:
        current = await SettingService.is_sales_open()
        new_value = "false" if current else "true"
        await SettingService.set_setting("sales_open", new_value)
        return not current
