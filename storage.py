from config import config
from database import Database
from sheets_database import build_sheets_db


def _build_storage():
    backend = (config.storage_backend or "sqlite").strip().lower()
    if backend == "sheets":
        return build_sheets_db()
    if backend == "sqlite":
        return Database(config.database_path)
    raise RuntimeError(
        f"Неизвестный STORAGE_BACKEND='{backend}'. Используйте 'sqlite' или 'sheets'."
    )


db = _build_storage()

