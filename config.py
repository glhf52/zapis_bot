from dataclasses import dataclass
import os

from dotenv import load_dotenv


load_dotenv()


@dataclass
class Config:
    """Основные настройки бота."""

    bot_token: str
    admin_id: int
    channel_id: int
    channel_link: str
    database_path: str = "database.sqlite3"
    main_menu_image: str = ""


def _required_env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(f"Не задана обязательная переменная окружения: {name}")
    return value


def load_config() -> Config:
    """Загрузка конфигурации только из переменных окружения."""
    BOT_TOKEN = _required_env("BOT_TOKEN")
    ADMIN_ID = int(_required_env("ADMIN_ID"))
    CHANNEL_ID = int(_required_env("CHANNEL_ID"))
    CHANNEL_LINK = _required_env("CHANNEL_LINK")
    DB_PATH = os.getenv("DB_PATH", "database.sqlite3")
    MAIN_MENU_IMAGE = os.getenv("MAIN_MENU_IMAGE", "")

    return Config(
        bot_token=BOT_TOKEN,
        admin_id=ADMIN_ID,
        channel_id=CHANNEL_ID,
        channel_link=CHANNEL_LINK,
        database_path=DB_PATH,
        main_menu_image=MAIN_MENU_IMAGE,
    )


config = load_config()

