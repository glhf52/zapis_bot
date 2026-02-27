import asyncio
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import config
from database import db
from handlers import router, schedule_reminder


async def restore_reminders(scheduler: AsyncIOScheduler, bot: Bot) -> None:
    """Восстановление задач напоминаний после перезапуска бота."""
    rows = await db.get_all_reminders()
    now = datetime.now()
    for r in rows:
        booking_id = r["booking_id"]
        run_at = datetime.fromisoformat(r["run_at"])
        user_tg_id = r["tg_id"]
        date_str = r["date"]
        time_str = r["time"]
        status = r["status"]

        if status != "active" or run_at <= now:
            # Если запись уже неактивна или время напоминания прошло — просто очищаем
            await db.delete_reminder(booking_id)
            continue

        await schedule_reminder(
            scheduler=scheduler,
            booking_id=booking_id,
            user_tg_id=user_tg_id,
            date_str=date_str,
            time_str=time_str,
            bot=bot,
        )


async def main() -> None:
    if not config.bot_token or config.bot_token == "PASTE_YOUR_BOT_TOKEN_HERE":
        raise RuntimeError("Укажите BOT_TOKEN в config.py или .env")

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.start()

    # Регистрация роутера с хендлерами
    dp.include_router(router)

    # Инициализация базы данных
    await db.init()

    # Восстановление задач напоминаний
    await restore_reminders(scheduler, bot)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(
        bot,
        allowed_updates=dp.resolve_used_update_types(),
        scheduler=scheduler,
    )


if __name__ == "__main__":
    asyncio.run(main())

