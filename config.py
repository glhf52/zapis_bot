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
    storage_backend: str = "sqlite"
    google_sheets_id: str = ""
    google_service_account_file: str = ""
    google_service_account_json: str = ""
    google_service_account_json_b64: str = ""


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
    STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "sqlite").strip().lower()
    GOOGLE_SHEETS_ID = os.getenv("GOOGLE_SHEETS_ID", "")
    GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "")
    GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    GOOGLE_SERVICE_ACCOUNT_JSON_B64 = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_B64", "")

    return Config(
        bot_token=BOT_TOKEN,
        admin_id=ADMIN_ID,
        channel_id=CHANNEL_ID,
        channel_link=CHANNEL_LINK,
        database_path=DB_PATH,
        main_menu_image=MAIN_MENU_IMAGE,
        storage_backend=STORAGE_BACKEND,
        google_sheets_id=GOOGLE_SHEETS_ID,
        google_service_account_file=GOOGLE_SERVICE_ACCOUNT_FILE,
        google_service_account_json=GOOGLE_SERVICE_ACCOUNT_JSON,
        google_service_account_json_b64=GOOGLE_SERVICE_ACCOUNT_JSON_B64,
    )


config = load_config()

