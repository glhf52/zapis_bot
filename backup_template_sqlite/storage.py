from config import config
from database import Database
from sheets_database import build_sheets_db


def _build_storage():
    backend = (config.storage_backend or "sqlite").strip().lower()
    if backend == "sheets":
        return build_sheets_db()
    return Database(config.database_path)


db = _build_storage()

