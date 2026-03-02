import aiosqlite
import os
from typing import Optional, List, Tuple
from datetime import datetime, date, time, timedelta

from config import config


class Database:
    """Обёртка над SQLite с асинхронными методами."""

    def __init__(self, path: str):
        self.path = path

    async def init(self) -> None:
        """Создание таблиц при старте бота."""
        # Если указан путь с директорией (например /data/database.sqlite3),
        # создаём директорию заранее для корректной работы на хостинге.
        if self.path and self.path != ":memory:":
            parent_dir = os.path.dirname(self.path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)

        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tg_id INTEGER UNIQUE NOT NULL,
                    name TEXT,
                    phone TEXT,
                    last_menu_message_id INTEGER
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS slots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,           -- YYYY-MM-DD
                    time TEXT NOT NULL,           -- HH:MM
                    is_available INTEGER NOT NULL DEFAULT 1,
                    doctor_id INTEGER,
                    procedure_id INTEGER
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS doctors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS procedures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS doctor_procedures (
                    doctor_id INTEGER NOT NULL,
                    procedure_id INTEGER NOT NULL,
                    PRIMARY KEY (doctor_id, procedure_id)
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS bookings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    slot_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id),
                    FOREIGN KEY (slot_id) REFERENCES slots(id)
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    booking_id INTEGER UNIQUE NOT NULL,
                    run_at TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    FOREIGN KEY (booking_id) REFERENCES bookings(id)
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            # Для уже существующих БД добавляем колонку last_menu_message_id, если её нет
            cur = await db.execute("PRAGMA table_info(users)")
            cols = await cur.fetchall()
            col_names = {c[1] for c in cols}
            if "last_menu_message_id" not in col_names:
                await db.execute(
                    "ALTER TABLE users ADD COLUMN last_menu_message_id INTEGER"
                )
            cur = await db.execute("PRAGMA table_info(slots)")
            slot_cols = await cur.fetchall()
            slot_col_names = {c[1] for c in slot_cols}
            if "doctor_id" not in slot_col_names:
                await db.execute("ALTER TABLE slots ADD COLUMN doctor_id INTEGER")
            if "procedure_id" not in slot_col_names:
                await db.execute("ALTER TABLE slots ADD COLUMN procedure_id INTEGER")

            # Тестовые данные (Вариант A), если справочники пустые
            cur = await db.execute("SELECT COUNT(*) FROM doctors")
            doctors_count = (await cur.fetchone())[0]
            if doctors_count == 0:
                await db.executemany(
                    "INSERT INTO doctors (name) VALUES (?)",
                    [
                        ("Иванов Андрей",),
                        ("Смирнова Анна",),
                        ("Петрова Мария",),
                    ],
                )
            cur = await db.execute("SELECT COUNT(*) FROM procedures")
            procedures_count = (await cur.fetchone())[0]
            if procedures_count == 0:
                await db.executemany(
                    "INSERT INTO procedures (name) VALUES (?)",
                    [
                        ("Осмотр",),
                        ("Лечение кариеса",),
                        ("Профессиональная чистка",),
                    ],
                )

            cur = await db.execute("SELECT COUNT(*) FROM doctor_procedures")
            rel_count = (await cur.fetchone())[0]
            if rel_count == 0:
                # Вариант A: все врачи делают все тестовые процедуры
                cur = await db.execute("SELECT id FROM doctors")
                doctors = await cur.fetchall()
                cur = await db.execute("SELECT id FROM procedures")
                procedures = await cur.fetchall()
                pairs = [(d[0], p[0]) for d in doctors for p in procedures]
                await db.executemany(
                    "INSERT INTO doctor_procedures (doctor_id, procedure_id) VALUES (?, ?)",
                    pairs,
                )
            await db.commit()

    async def get_or_create_user(self, tg_id: int) -> int:
        """Вернуть ID пользователя в БД, создавая запись при необходимости."""
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT id FROM users WHERE tg_id = ?", (tg_id,))
            row = await cur.fetchone()
            if row:
                return row["id"]

            await db.execute(
                "INSERT INTO users (tg_id) VALUES (?)",
                (tg_id,),
            )
            await db.commit()
            cur = await db.execute("SELECT id FROM users WHERE tg_id = ?", (tg_id,))
            row = await cur.fetchone()
            return row["id"]

    async def update_user_info(self, tg_id: int, name: str, phone: str) -> None:
        """Сохранить имя и телефон пользователя."""
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE users SET name = ?, phone = ? WHERE tg_id = ?",
                (name, phone, tg_id),
            )
            await db.commit()

    async def get_last_menu_message_id(self, tg_id: int) -> Optional[int]:
        """Получить ID последнего сообщения главного меню пользователя."""
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT last_menu_message_id FROM users WHERE tg_id = ?",
                (tg_id,),
            )
            row = await cur.fetchone()
            if not row:
                return None
            return row["last_menu_message_id"]

    async def set_last_menu_message_id(self, tg_id: int, message_id: int) -> None:
        """Сохранить ID последнего сообщения главного меню пользователя."""
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE users SET last_menu_message_id = ? WHERE tg_id = ?",
                (message_id, tg_id),
            )
            await db.commit()

    async def get_active_booking_by_tg(self, tg_id: int) -> Optional[aiosqlite.Row]:
        """Получить активную запись пользователя, если она есть."""
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT b.*, s.date, s.time, d.name as doctor_name, p.name as procedure_name
                FROM bookings b
                JOIN users u ON u.id = b.user_id
                JOIN slots s ON s.id = b.slot_id
                LEFT JOIN doctors d ON d.id = s.doctor_id
                LEFT JOIN procedures p ON p.id = s.procedure_id
                WHERE u.tg_id = ? AND b.status = 'active'
                """,
                (tg_id,),
            )
            return await cur.fetchone()

    async def create_slot(
        self, d: date, t: time, doctor_id: int, procedure_id: int
    ) -> None:
        """Создать один временной слот (для админ-панели)."""
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO slots (date, time, is_available, doctor_id, procedure_id)
                VALUES (?, ?, 1, ?, ?)
                """,
                (d.isoformat(), t.strftime("%H:%M"), doctor_id, procedure_id),
            )
            await db.commit()

    async def delete_slot(self, slot_id: int) -> None:
        """Удалить слот (если по нему нет активных записей)."""
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM slots WHERE id = ?", (slot_id,))
            await db.commit()

    async def close_day(self, d: date) -> None:
        """Полностью закрыть день: сделать все слоты недоступными."""
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "UPDATE slots SET is_available = 0 WHERE date = ?", (d.isoformat(),)
            )
            await db.commit()

    async def get_available_days(
        self, procedure_id: Optional[int] = None, doctor_id: Optional[int] = None
    ) -> List[str]:
        """Дни, в которых есть свободные слоты в течение ближайших 30 дней."""
        today = date.today()
        # 31 день вперёд (включая сегодня), только будни
        limit_date = today + timedelta(days=31)
        days: List[str] = []
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            query = """
                SELECT DISTINCT date
                FROM slots
                WHERE is_available = 1
            """
            params: list = []
            if procedure_id is not None:
                query += " AND procedure_id = ?"
                params.append(procedure_id)
            if doctor_id is not None:
                query += " AND doctor_id = ?"
                params.append(doctor_id)
            query += " ORDER BY date"
            cur = await db.execute(query, tuple(params))
            rows = await cur.fetchall()
            for r in rows:
                d = date.fromisoformat(r["date"])
                # исключаем выходные (суббота=5, воскресенье=6)
                if today <= d <= limit_date and d.weekday() < 5:
                    days.append(r["date"])
        return days

    async def get_available_times(
        self, d: date, procedure_id: Optional[int] = None, doctor_id: Optional[int] = None
    ) -> List[aiosqlite.Row]:
        """Свободные слоты на конкретную дату."""
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            query = """
                SELECT id, time
                FROM slots
                WHERE date = ? AND is_available = 1
            """
            params: list = [d.isoformat()]
            if procedure_id is not None:
                query += " AND procedure_id = ?"
                params.append(procedure_id)
            if doctor_id is not None:
                query += " AND doctor_id = ?"
                params.append(doctor_id)
            query += " ORDER BY time"
            cur = await db.execute(query, tuple(params))
            return await cur.fetchall()

    async def book_slot(self, tg_id: int, slot_id: int) -> Optional[int]:
        """Создать запись на слот. Возвращает ID бронирования или None, если уже есть активная запись."""
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row

            # Проверяем, есть ли у пользователя активная запись
            cur = await db.execute(
                """
                SELECT b.id
                FROM bookings b
                JOIN users u ON u.id = b.user_id
                WHERE u.tg_id = ? AND b.status = 'active'
                """,
                (tg_id,),
            )
            if await cur.fetchone():
                return None

            user_id = await self.get_or_create_user(tg_id)

            # Забираем слот
            cur = await db.execute(
                "SELECT is_available FROM slots WHERE id = ?", (slot_id,)
            )
            slot_row = await cur.fetchone()
            if not slot_row or slot_row["is_available"] == 0:
                return None

            await db.execute(
                "UPDATE slots SET is_available = 0 WHERE id = ?", (slot_id,)
            )
            now = datetime.now().isoformat()
            await db.execute(
                """
                INSERT INTO bookings (user_id, slot_id, status, created_at)
                VALUES (?, ?, 'active', ?)
                """,
                (user_id, slot_id, now),
            )
            await db.commit()

            cur = await db.execute(
                "SELECT id FROM bookings WHERE user_id = ? AND slot_id = ? AND status = 'active'",
                (user_id, slot_id,),
            )
            row = await cur.fetchone()
            return row["id"] if row else None

    async def cancel_booking(self, booking_id: int) -> Optional[Tuple[str, str]]:
        """Отменить запись и снова открыть слот. Возвращает (date, time) слота."""
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT slot_id
                FROM bookings
                WHERE id = ? AND status = 'active'
                """,
                (booking_id,),
            )
            row = await cur.fetchone()
            if not row:
                return None
            slot_id = row["slot_id"]

            await db.execute(
                "UPDATE bookings SET status = 'cancelled' WHERE id = ?",
                (booking_id,),
            )
            await db.execute(
                "UPDATE slots SET is_available = 1 WHERE id = ?",
                (slot_id,),
            )
            await db.commit()

            cur = await db.execute(
                "SELECT date, time FROM slots WHERE id = ?", (slot_id,)
            )
            slot_row = await cur.fetchone()
            if not slot_row:
                return None
            return slot_row["date"], slot_row["time"]

    async def get_booking_for_reminders(self) -> List[aiosqlite.Row]:
        """Список активных записей с их слотами, для восстановления задач напоминаний."""
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT b.id as booking_id,
                       u.tg_id as tg_id,
                       s.date as date,
                       s.time as time
                FROM bookings b
                JOIN users u ON u.id = b.user_id
                JOIN slots s ON s.id = b.slot_id
                WHERE b.status = 'active'
                """
            )
            return await cur.fetchall()

    async def save_reminder(self, booking_id: int, run_at: datetime, job_id: str) -> None:
        """Сохранить задачу напоминания."""
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO reminders (booking_id, run_at, job_id)
                VALUES (?, ?, ?)
                """,
                (booking_id, run_at.isoformat(), job_id),
            )
            await db.commit()

    async def delete_reminder(self, booking_id: int) -> Optional[str]:
        """Удалить задачу напоминания, вернуть job_id."""
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT job_id FROM reminders WHERE booking_id = ?", (booking_id,)
            )
            row = await cur.fetchone()
            if not row:
                return None
            job_id = row["job_id"]
            await db.execute(
                "DELETE FROM reminders WHERE booking_id = ?", (booking_id,)
            )
            await db.commit()
            return job_id

    async def get_all_reminders(self) -> List[aiosqlite.Row]:
        """Получить все сохранённые напоминания."""
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT r.booking_id,
                       r.run_at,
                       b.status,
                       u.tg_id,
                       s.date,
                       s.time
                FROM reminders r
                JOIN bookings b ON b.id = r.booking_id
                JOIN users u ON u.id = b.user_id
                JOIN slots s ON s.id = b.slot_id
                """
            )
            return await cur.fetchall()

    async def get_slot(self, slot_id: int) -> Optional[aiosqlite.Row]:
        """Получить слот по ID."""
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT s.id, s.date, s.time, s.is_available,
                       d.name as doctor_name, p.name as procedure_name
                FROM slots s
                LEFT JOIN doctors d ON d.id = s.doctor_id
                LEFT JOIN procedures p ON p.id = s.procedure_id
                WHERE s.id = ?
                """,
                (slot_id,),
            )
            return await cur.fetchone()

    async def get_bookings_for_day(self, d: date) -> List[aiosqlite.Row]:
        """Получить активные записи на указанную дату (для админа)."""
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT b.id as booking_id,
                       s.time as time,
                       u.name as name,
                       u.phone as phone,
                       u.tg_id as tg_id,
                       d.name as doctor_name,
                       p.name as procedure_name
                FROM bookings b
                JOIN slots s ON s.id = b.slot_id
                JOIN users u ON u.id = b.user_id
                LEFT JOIN doctors d ON d.id = s.doctor_id
                LEFT JOIN procedures p ON p.id = s.procedure_id
                WHERE s.date = ? AND b.status = 'active'
                ORDER BY s.time
                """,
                (d.isoformat(),),
            )
            return await cur.fetchall()

    async def get_booking_info(self, booking_id: int) -> Optional[aiosqlite.Row]:
        """Получить подробную информацию о бронировании по ID (для уведомлений)."""
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT b.id as booking_id,
                       u.tg_id as tg_id,
                       u.name as name,
                       u.phone as phone,
                       s.date as date,
                       s.time as time,
                       d.name as doctor_name,
                       p.name as procedure_name
                FROM bookings b
                JOIN users u ON u.id = b.user_id
                JOIN slots s ON s.id = b.slot_id
                LEFT JOIN doctors d ON d.id = s.doctor_id
                LEFT JOIN procedures p ON p.id = s.procedure_id
                WHERE b.id = ?
                """,
                (booking_id,),
            )
            return await cur.fetchone()

    async def get_procedures(self) -> List[aiosqlite.Row]:
        """Список процедур."""
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT id, name FROM procedures ORDER BY name")
            return await cur.fetchall()

    async def get_doctors_for_procedure(self, procedure_id: int) -> List[aiosqlite.Row]:
        """Список врачей, которые делают выбранную процедуру."""
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT d.id, d.name
                FROM doctors d
                JOIN doctor_procedures dp ON dp.doctor_id = d.id
                WHERE dp.procedure_id = ?
                ORDER BY d.name
                """,
                (procedure_id,),
            )
            return await cur.fetchall()

    async def set_setting(self, key: str, value: str) -> None:
        """Сохранить произвольную настройку."""
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )
            await db.commit()

    async def get_setting(self, key: str) -> Optional[str]:
        """Получить настройку по ключу."""
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT value FROM settings WHERE key = ?",
                (key,),
            )
            row = await cur.fetchone()
            return row["value"] if row else None

    async def get_slot_days(self) -> List[str]:
        """Получить даты, на которые есть слоты (для админских кнопок)."""
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT DISTINCT date
                FROM slots
                ORDER BY date
                """
            )
            rows = await cur.fetchall()
            return [row["date"] for row in rows]

    async def get_day_schedule(self, d: date) -> List[aiosqlite.Row]:
        """Полное расписание на день: все слоты + статус + клиент."""
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT s.id as slot_id,
                       s.time as time,
                       s.is_available as is_available,
                       d.name as doctor_name,
                       p.name as procedure_name,
                       b.id as booking_id,
                       u.name as client_name,
                       u.phone as client_phone
                FROM slots s
                LEFT JOIN doctors d ON d.id = s.doctor_id
                LEFT JOIN procedures p ON p.id = s.procedure_id
                LEFT JOIN bookings b ON b.slot_id = s.id AND b.status = 'active'
                LEFT JOIN users u ON u.id = b.user_id
                WHERE s.date = ?
                ORDER BY s.time
                """,
                (d.isoformat(),),
            )
            return await cur.fetchall()

    async def clear_slots(self, mode: str) -> tuple[int, list[int]]:
        """
        Очистить слоты по режиму:
        - free: только свободные
        - booked: только занятые (с активной записью)
        - all: все слоты
        Возвращает (кол-во удалённых слотов, список booking_id для снятия reminder jobs).
        """
        if mode not in {"free", "booked", "all"}:
            return 0, []

        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row

            if mode == "free":
                cur = await db.execute(
                    """
                    SELECT s.id
                    FROM slots s
                    LEFT JOIN bookings b ON b.slot_id = s.id AND b.status = 'active'
                    WHERE s.is_available = 1 AND b.id IS NULL
                    """
                )
            elif mode == "booked":
                cur = await db.execute(
                    """
                    SELECT DISTINCT s.id
                    FROM slots s
                    JOIN bookings b ON b.slot_id = s.id AND b.status = 'active'
                    """
                )
            else:
                cur = await db.execute("SELECT id FROM slots")

            slot_rows = await cur.fetchall()
            slot_ids = [int(r["id"]) for r in slot_rows]
            if not slot_ids:
                return 0, []

            placeholders = ",".join(["?"] * len(slot_ids))

            cur = await db.execute(
                f"""
                SELECT id
                FROM bookings
                WHERE status = 'active' AND slot_id IN ({placeholders})
                """,
                tuple(slot_ids),
            )
            booking_rows = await cur.fetchall()
            booking_ids = [int(r["id"]) for r in booking_rows]

            if booking_ids:
                reminder_ph = ",".join(["?"] * len(booking_ids))
                await db.execute(
                    f"DELETE FROM reminders WHERE booking_id IN ({reminder_ph})",
                    tuple(booking_ids),
                )

            await db.execute(
                f"DELETE FROM bookings WHERE slot_id IN ({placeholders})",
                tuple(slot_ids),
            )
            await db.execute(
                f"DELETE FROM slots WHERE id IN ({placeholders})",
                tuple(slot_ids),
            )
            await db.commit()
            return len(slot_ids), booking_ids


db = Database(config.database_path)

