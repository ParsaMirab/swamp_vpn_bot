from dataclasses import dataclass
from pathlib import Path
from typing import Final
import os

from dotenv import load_dotenv


BASE_DIR: Final[Path] = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is not configured in .env")
    return value


def _get_admin_id() -> int:
    admin_id = os.getenv("ADMIN_ID")
    if admin_id and admin_id.strip().isdigit():
        return int(admin_id.strip())

    admin_ids = os.getenv("ADMIN_IDS", "")
    first_admin_id = next(
        (item.strip() for item in admin_ids.split(",") if item.strip().isdigit()),
        None,
    )
    if first_admin_id:
        return int(first_admin_id)

    raise RuntimeError("ADMIN_ID is not configured in .env")


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    admin_id: int
    database_url: str


DATABASE_DIR: Final[Path] = BASE_DIR / "database"
DATABASE_DIR.mkdir(exist_ok=True)

settings = Settings(
    bot_token=_get_required_env("BOT_TOKEN"),
    admin_id=_get_admin_id(),
    database_url=os.getenv(
        "DATABASE_URL",
        f"sqlite+aiosqlite:///{(DATABASE_DIR / 'database.db').as_posix()}",
    ),
)
