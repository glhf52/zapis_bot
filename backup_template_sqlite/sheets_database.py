import asyncio
from datetime import date, datetime, time, timedelta
from typing import Any, Optional

import gspread

from config import config


class SheetsDatabase:
    """Google Sheets backend with sqlite-like async interface."""

    SHEETS_HEADERS = {
        "users": ["tg_id", "name", "phone", "last_menu_message_id"],
        "doctors": ["doctor_id", "name", "active"],
        "procedures": ["procedure_id", "name", "active"],
        "doctor_procedures": ["doctor_id", "procedure_id"],
        "slots": [
            "slot_id",
            "date",
            "time",
            "doctor_id",
            "procedure_id",
            "status",
            "source",
            "client_name",
            "client_phone",
            "tg_id",
            "created_at",
        ],
        "settings": ["key", "value"],
    }

    def __init__(self, spreadsheet_id: str, service_account_file: str):
        self.spreadsheet_id = spreadsheet_id
        self.service_account_file = service_account_file
        self.gc = None
        self.sh = None

    async def _ensure_client(self) -> None:
        if self.gc and self.sh:
            return

        def _connect():
            gc = gspread.service_account(filename=self.service_account_file)
            sh = gc.open_by_key(self.spreadsheet_id)
            return gc, sh

        self.gc, self.sh = await asyncio.to_thread(_connect)

    async def _ensure_sheet(self, title: str) -> None:
        await self._ensure_client()
        headers = self.SHEETS_HEADERS[title]

        def _op():
            try:
                ws = self.sh.worksheet(title)
            except gspread.WorksheetNotFound:
                ws = self.sh.add_worksheet(title=title, rows=1000, cols=len(headers) + 5)
            first_row = ws.row_values(1)
            if first_row != headers:
                ws.clear()
                ws.append_row(headers, value_input_option="RAW")
            return ws

        await asyncio.to_thread(_op)

    async def _records(self, title: str) -> list[dict[str, Any]]:
        await self._ensure_sheet(title)

        def _op():
            ws = self.sh.worksheet(title)
            return ws.get_all_records()

        return await asyncio.to_thread(_op)

    async def _append(self, title: str, row_map: dict[str, Any]) -> None:
        await self._ensure_sheet(title)
        headers = self.SHEETS_HEADERS[title]
        row = [row_map.get(h, "") for h in headers]

        def _op():
            ws = self.sh.worksheet(title)
            ws.append_row(row, value_input_option="RAW")

        await asyncio.to_thread(_op)

    async def _find_row_idx_by_key(
        self, title: str, key: str, value: Any
    ) -> tuple[Optional[int], Optional[dict[str, Any]]]:
        records = await self._records(title)
        for idx, rec in enumerate(records, start=2):
            if str(rec.get(key, "")) == str(value):
                return idx, rec
        return None, None

    async def _update_row(self, title: str, row_idx: int, updates: dict[str, Any]) -> None:
        await self._ensure_sheet(title)
        headers = self.SHEETS_HEADERS[title]

        def _op():
            ws = self.sh.worksheet(title)
            for k, v in updates.items():
                if k not in headers:
                    continue
                col = headers.index(k) + 1
                ws.update_cell(row_idx, col, v)

        await asyncio.to_thread(_op)

    async def _delete_row(self, title: str, row_idx: int) -> None:
        await self._ensure_sheet(title)

        def _op():
            ws = self.sh.worksheet(title)
            ws.delete_rows(row_idx)

        await asyncio.to_thread(_op)

    async def _next_id(self, title: str, id_field: str) -> int:
        records = await self._records(title)
        max_id = 0
        for rec in records:
            try:
                max_id = max(max_id, int(rec.get(id_field) or 0))
            except Exception:
                continue
        return max_id + 1

    async def init(self) -> None:
        for title in self.SHEETS_HEADERS:
            await self._ensure_sheet(title)

        doctors = await self._records("doctors")
        if not doctors:
            for i, name in enumerate(
                ["Иванов Андрей", "Смирнова Анна", "Петрова Мария"], start=1
            ):
                await self._append(
                    "doctors", {"doctor_id": i, "name": name, "active": "1"}
                )

        procedures = await self._records("procedures")
        if not procedures:
            for i, name in enumerate(
                ["Осмотр", "Лечение кариеса", "Профессиональная чистка"], start=1
            ):
                await self._append(
                    "procedures", {"procedure_id": i, "name": name, "active": "1"}
                )

        links = await self._records("doctor_procedures")
        if not links:
            doctors = await self._records("doctors")
            procedures = await self._records("procedures")
            for d in doctors:
                for p in procedures:
                    await self._append(
                        "doctor_procedures",
                        {
                            "doctor_id": d["doctor_id"],
                            "procedure_id": p["procedure_id"],
                        },
                    )

    async def get_or_create_user(self, tg_id: int) -> int:
        row_idx, rec = await self._find_row_idx_by_key("users", "tg_id", tg_id)
        if rec:
            return int(rec["tg_id"])
        await self._append(
            "users",
            {
                "tg_id": tg_id,
                "name": "",
                "phone": "",
                "last_menu_message_id": "",
            },
        )
        return tg_id

    async def update_user_info(self, tg_id: int, name: str, phone: str) -> None:
        row_idx, _ = await self._find_row_idx_by_key("users", "tg_id", tg_id)
        if not row_idx:
            await self.get_or_create_user(tg_id)
            row_idx, _ = await self._find_row_idx_by_key("users", "tg_id", tg_id)
        await self._update_row("users", row_idx, {"name": name, "phone": phone})

    async def get_last_menu_message_id(self, tg_id: int) -> Optional[int]:
        _, rec = await self._find_row_idx_by_key("users", "tg_id", tg_id)
        if not rec:
            return None
        value = str(rec.get("last_menu_message_id") or "").strip()
        return int(value) if value.isdigit() else None

    async def set_last_menu_message_id(self, tg_id: int, message_id: int) -> None:
        row_idx, _ = await self._find_row_idx_by_key("users", "tg_id", tg_id)
        if not row_idx:
            await self.get_or_create_user(tg_id)
            row_idx, _ = await self._find_row_idx_by_key("users", "tg_id", tg_id)
        await self._update_row("users", row_idx, {"last_menu_message_id": str(message_id)})

    async def get_procedures(self) -> list[dict[str, Any]]:
        rows = await self._records("procedures")
        out = []
        for r in rows:
            if str(r.get("active", "1")) == "0":
                continue
            out.append({"id": int(r["procedure_id"]), "name": r["name"]})
        return out

    async def get_doctors_for_procedure(self, procedure_id: int) -> list[dict[str, Any]]:
        doctors = await self._records("doctors")
        links = await self._records("doctor_procedures")
        allowed = {
            str(l["doctor_id"])
            for l in links
            if str(l.get("procedure_id", "")) == str(procedure_id)
        }
        out = []
        for d in doctors:
            if str(d.get("active", "1")) == "0":
                continue
            if str(d["doctor_id"]) in allowed:
                out.append({"id": int(d["doctor_id"]), "name": d["name"]})
        out.sort(key=lambda x: x["name"])
        return out

    async def create_slot(
        self, d: date, t: time, doctor_id: int, procedure_id: int
    ) -> None:
        slot_id = await self._next_id("slots", "slot_id")
        await self._append(
            "slots",
            {
                "slot_id": slot_id,
                "date": d.isoformat(),
                "time": t.strftime("%H:%M"),
                "doctor_id": doctor_id,
                "procedure_id": procedure_id,
                "status": "free",
                "source": "admin",
                "client_name": "",
                "client_phone": "",
                "tg_id": "",
                "created_at": datetime.now().isoformat(),
            },
        )

    async def delete_slot(self, slot_id: int) -> None:
        row_idx, rec = await self._find_row_idx_by_key("slots", "slot_id", slot_id)
        if not row_idx or not rec:
            return
        if rec.get("status") == "booked":
            return
        await self._delete_row("slots", row_idx)

    async def close_day(self, d: date) -> None:
        rows = await self._records("slots")
        for idx, rec in enumerate(rows, start=2):
            if rec.get("date") == d.isoformat() and rec.get("status") == "free":
                await self._update_row("slots", idx, {"status": "blocked"})

    async def get_available_days(
        self, procedure_id: Optional[int] = None, doctor_id: Optional[int] = None
    ) -> list[str]:
        today = date.today()
        limit_date = today + timedelta(days=31)
        rows = await self._records("slots")
        days = set()
        for r in rows:
            if r.get("status") != "free":
                continue
            if procedure_id is not None and str(r.get("procedure_id")) != str(procedure_id):
                continue
            if doctor_id is not None and str(r.get("doctor_id")) != str(doctor_id):
                continue
            try:
                d = date.fromisoformat(r["date"])
            except Exception:
                continue
            if today <= d <= limit_date and d.weekday() < 5:
                days.add(r["date"])
        return sorted(days)

    async def get_available_times(
        self, d: date, procedure_id: Optional[int] = None, doctor_id: Optional[int] = None
    ) -> list[dict[str, Any]]:
        rows = await self._records("slots")
        out = []
        for r in rows:
            if r.get("date") != d.isoformat() or r.get("status") != "free":
                continue
            if procedure_id is not None and str(r.get("procedure_id")) != str(procedure_id):
                continue
            if doctor_id is not None and str(r.get("doctor_id")) != str(doctor_id):
                continue
            out.append({"id": int(r["slot_id"]), "time": r["time"]})
        out.sort(key=lambda x: x["time"])
        return out

    async def book_slot(self, tg_id: int, slot_id: int) -> Optional[int]:
        rows = await self._records("slots")
        # Один активный слот на пользователя
        for r in rows:
            if str(r.get("tg_id", "")) == str(tg_id) and r.get("status") == "booked":
                return None

        row_idx, rec = await self._find_row_idx_by_key("slots", "slot_id", slot_id)
        if not row_idx or not rec or rec.get("status") != "free":
            return None

        _, user = await self._find_row_idx_by_key("users", "tg_id", tg_id)
        user_name = (user or {}).get("name", "")
        user_phone = (user or {}).get("phone", "")

        await self._update_row(
            "slots",
            row_idx,
            {
                "status": "booked",
                "source": "bot",
                "client_name": user_name,
                "client_phone": user_phone,
                "tg_id": str(tg_id),
            },
        )
        return int(slot_id)

    async def cancel_booking(self, booking_id: int) -> Optional[tuple[str, str]]:
        row_idx, rec = await self._find_row_idx_by_key("slots", "slot_id", booking_id)
        if not row_idx or not rec or rec.get("status") != "booked":
            return None
        await self._update_row(
            "slots",
            row_idx,
            {
                "status": "free",
                "source": "",
                "client_name": "",
                "client_phone": "",
                "tg_id": "",
            },
        )
        return rec["date"], rec["time"]

    async def get_booking_for_reminders(self) -> list[dict[str, Any]]:
        rows = await self._records("slots")
        out = []
        for r in rows:
            if r.get("status") != "booked" or not str(r.get("tg_id", "")).strip():
                continue
            out.append(
                {
                    "booking_id": int(r["slot_id"]),
                    "tg_id": int(r["tg_id"]),
                    "date": r["date"],
                    "time": r["time"],
                }
            )
        return out

    async def get_slot(self, slot_id: int) -> Optional[dict[str, Any]]:
        _, rec = await self._find_row_idx_by_key("slots", "slot_id", slot_id)
        if not rec:
            return None
        doctors = await self._records("doctors")
        procedures = await self._records("procedures")
        doctor_name = next(
            (d["name"] for d in doctors if str(d["doctor_id"]) == str(rec.get("doctor_id"))),
            None,
        )
        procedure_name = next(
            (
                p["name"]
                for p in procedures
                if str(p["procedure_id"]) == str(rec.get("procedure_id"))
            ),
            None,
        )
        return {
            "id": int(rec["slot_id"]),
            "date": rec["date"],
            "time": rec["time"],
            "is_available": 1 if rec.get("status") == "free" else 0,
            "doctor_name": doctor_name,
            "procedure_name": procedure_name,
        }

    async def get_active_booking_by_tg(self, tg_id: int) -> Optional[dict[str, Any]]:
        rows = await self._records("slots")
        for r in rows:
            if str(r.get("tg_id", "")) == str(tg_id) and r.get("status") == "booked":
                slot = await self.get_slot(int(r["slot_id"]))
                if not slot:
                    return None
                return {
                    "id": int(r["slot_id"]),
                    "date": slot["date"],
                    "time": slot["time"],
                    "doctor_name": slot.get("doctor_name"),
                    "procedure_name": slot.get("procedure_name"),
                }
        return None

    async def get_bookings_for_day(self, d: date) -> list[dict[str, Any]]:
        rows = await self._records("slots")
        out = []
        for r in rows:
            if r.get("date") != d.isoformat() or r.get("status") != "booked":
                continue
            slot = await self.get_slot(int(r["slot_id"]))
            out.append(
                {
                    "booking_id": int(r["slot_id"]),
                    "time": r["time"],
                    "name": r.get("client_name", ""),
                    "phone": r.get("client_phone", ""),
                    "tg_id": int(r["tg_id"]) if str(r.get("tg_id", "")).isdigit() else None,
                    "doctor_name": slot.get("doctor_name") if slot else None,
                    "procedure_name": slot.get("procedure_name") if slot else None,
                }
            )
        out.sort(key=lambda x: x["time"])
        return out

    async def get_booking_info(self, booking_id: int) -> Optional[dict[str, Any]]:
        _, rec = await self._find_row_idx_by_key("slots", "slot_id", booking_id)
        if not rec:
            return None
        slot = await self.get_slot(booking_id)
        return {
            "booking_id": booking_id,
            "tg_id": int(rec["tg_id"]) if str(rec.get("tg_id", "")).isdigit() else None,
            "name": rec.get("client_name", ""),
            "phone": rec.get("client_phone", ""),
            "date": rec["date"],
            "time": rec["time"],
            "doctor_name": slot.get("doctor_name") if slot else None,
            "procedure_name": slot.get("procedure_name") if slot else None,
        }

    async def set_setting(self, key: str, value: str) -> None:
        row_idx, _ = await self._find_row_idx_by_key("settings", "key", key)
        if row_idx:
            await self._update_row("settings", row_idx, {"value": value})
        else:
            await self._append("settings", {"key": key, "value": value})

    async def get_setting(self, key: str) -> Optional[str]:
        _, rec = await self._find_row_idx_by_key("settings", "key", key)
        return rec.get("value") if rec else None

    async def get_slot_days(self) -> list[str]:
        rows = await self._records("slots")
        return sorted({r["date"] for r in rows if r.get("date")})

    async def get_day_schedule(self, d: date) -> list[dict[str, Any]]:
        rows = await self._records("slots")
        out = []
        for r in rows:
            if r.get("date") != d.isoformat():
                continue
            slot = await self.get_slot(int(r["slot_id"]))
            is_available = 1 if r.get("status") == "free" else 0
            out.append(
                {
                    "slot_id": int(r["slot_id"]),
                    "time": r["time"],
                    "is_available": is_available,
                    "doctor_name": slot.get("doctor_name") if slot else None,
                    "procedure_name": slot.get("procedure_name") if slot else None,
                    "booking_id": int(r["slot_id"]) if r.get("status") == "booked" else None,
                    "client_name": r.get("client_name", ""),
                    "client_phone": r.get("client_phone", ""),
                }
            )
        out.sort(key=lambda x: x["time"])
        return out

    # Backward compatibility no-ops
    async def save_reminder(self, booking_id: int, run_at: datetime, job_id: str) -> None:
        return

    async def delete_reminder(self, booking_id: int) -> Optional[str]:
        return None

    async def get_all_reminders(self) -> list[dict[str, Any]]:
        return []


def build_sheets_db() -> SheetsDatabase:
    if not config.google_sheets_id or not config.google_service_account_file:
        raise RuntimeError(
            "Для STORAGE_BACKEND=sheets задайте GOOGLE_SHEETS_ID и GOOGLE_SERVICE_ACCOUNT_FILE"
        )
    return SheetsDatabase(
        spreadsheet_id=config.google_sheets_id,
        service_account_file=config.google_service_account_file,
    )

