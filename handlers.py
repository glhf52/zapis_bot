from __future__ import annotations

import os
from datetime import datetime, date, time, timedelta

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.utils.formatting import Bold, as_marked_section
from aiogram.exceptions import TelegramBadRequest

from config import config
from database import db
from keyboards import (
    main_menu_keyboard,
    subscription_check_keyboard,
    booking_days_keyboard,
    booking_times_keyboard,
    confirm_booking_keyboard,
    cancel_my_booking_keyboard,
    admin_panel_keyboard,
    portfolio_keyboard,
)
from states import BookingStates, AdminStates


router = Router()

MAIN_MENU_TEXT = (
    "<b>Привет!</b>\n\n"
    "Я бот для записи В нашу Стоматология Green Aple\n"
    "Выберите нужный раздел в меню ниже!"
)

# Резервная картинка для главного меню (если MAIN_MENU_IMAGE не задан в окружении)
DEFAULT_MAIN_MENU_IMAGE = (
    "AgACAgIAAxkBAAFDZo9pog5aMzggOdMP-oPWa0_oGNGVcgACChJrGwlKEUkTxsFDGN3DogEAAwIAA3gAAzoE"
)


async def send_main_menu(message: Message, user_id: int) -> None:
    """Показ главного меню с картинкой (если задан MAIN_MENU_IMAGE)."""
    is_admin = user_id == config.admin_id
    kb = main_menu_keyboard(is_admin=is_admin)

    image_source = (config.main_menu_image or "").strip() or DEFAULT_MAIN_MENU_IMAGE
    if image_source:
        try:
            image_value = image_source
            if image_value.startswith(("http://", "https://")):
                photo = image_value
            elif os.path.exists(image_value):
                photo = FSInputFile(image_value)
            else:
                # Позволяем передавать file_id из Telegram через MAIN_MENU_IMAGE
                photo = image_value
            await message.answer_photo(photo=photo, caption=MAIN_MENU_TEXT, reply_markup=kb)
            return
        except Exception as e:
            # Если картинка недоступна/путь неверный — показываем обычное меню текстом.
            # Логируем причину для диагностики на хостинге.
            print(f"[MAIN_MENU_IMAGE] send photo failed: {e}")

    await message.answer(MAIN_MENU_TEXT, reply_markup=kb)


async def safe_edit_text(
    message: Message | CallbackQuery,
    text: str,
    reply_markup=None,
) -> None:
    """
    Безопасное изменение текста сообщения.
    Игнорирует ошибку "message is not modified".
    """
    # На вход может прийти объект Message или CallbackQuery.message
    msg = message.message if isinstance(message, CallbackQuery) else message
    try:
        if msg.photo:
            await msg.edit_caption(caption=text, reply_markup=reply_markup)
        else:
            await msg.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            return
        raise


async def check_subscription(user_id: int, bot) -> bool:
    """Проверка подписки пользователя на канал."""
    try:
        member = await bot.get_chat_member(config.channel_id, user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception:
        # Если не удалось проверить (например, бот не админ канала) — считаем, что подписка есть,
        # чтобы не ломать сценарий.
        return True


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    """Стартовое сообщение и главное меню."""
    await state.clear()
    await send_main_menu(message, message.from_user.id)


@router.message(F.photo)
async def get_photo_file_id(message: Message) -> None:
    """
    Утилита для админа:
    отправьте боту фото, и он вернёт file_id (самый большой размер).
    """
    if message.from_user.id != config.admin_id:
        return
    file_id = message.photo[-1].file_id
    await message.answer(
        "<b>file_id для MAIN_MENU_IMAGE:</b>\n"
        f"<code>{file_id}</code>"
    )


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await safe_edit_text(
        callback,
        MAIN_MENU_TEXT,
        reply_markup=main_menu_keyboard(is_admin=callback.from_user.id == config.admin_id),
    )


@router.callback_query(F.data == "menu_prices")
async def show_prices(callback: CallbackQuery) -> None:
    """Прайсы (без FSM)."""
    text = (
        "<b>Прайс-лист</b>\n\n"
        "Френч — <b>1000₽</b>\n"
        "Квадрат — <b>500₽</b>"
    )
    await safe_edit_text(
        callback,
        text,
        reply_markup=main_menu_keyboard(
            is_admin=callback.from_user.id == config.admin_id
        ),
    )


@router.callback_query(F.data == "menu_portfolio")
async def show_portfolio(callback: CallbackQuery) -> None:
    """Портфолио (без FSM, только кнопка-ссылка)."""
    text = "<b>Портфолио</b>\n\nНажмите кнопку ниже, чтобы посмотреть работы."
    await safe_edit_text(callback, text, reply_markup=portfolio_keyboard())


@router.callback_query(F.data == "menu_book")
async def start_booking(callback: CallbackQuery, state: FSMContext, bot) -> None:
    """Начало процесса записи: проверка подписки, затем выбор даты."""
    if not await check_subscription(callback.from_user.id, bot):
        await safe_edit_text(
            callback,
            "Для записи необходимо подписаться на канал.",
            reply_markup=subscription_check_keyboard(config.channel_link),
        )
        return

    await state.set_state(BookingStates.choosing_date)
    days = await db.get_available_days()
    if not days:
        await safe_edit_text(
            callback,
            "К сожалению, сейчас нет доступных слотов для записи.\n"
            "Попробуйте позже или свяжитесь с мастером.",
            reply_markup=main_menu_keyboard(
                is_admin=callback.from_user.id == config.admin_id
            ),
        )
        return

    await safe_edit_text(
        callback,
        "<b>Выберите дату</b> для записи (в течение ближайшего месяца):",
        reply_markup=booking_days_keyboard(days),
    )


@router.callback_query(F.data == "check_subscription")
async def recheck_subscription(callback: CallbackQuery, bot, state: FSMContext) -> None:
    """Повторная проверка подписки."""
    if not await check_subscription(callback.from_user.id, bot):
        await callback.answer("Подписка не найдена, проверьте ещё раз.", show_alert=True)
        return

    await safe_edit_text(
        callback,
        "<b>Спасибо за подписку!</b>\nТеперь можно записаться на маникюр.",
        reply_markup=main_menu_keyboard(
            is_admin=callback.from_user.id == config.admin_id
        ),
    )
    await state.clear()


@router.callback_query(BookingStates.choosing_date, F.data.startswith("book_day:"))
async def choose_day(callback: CallbackQuery, state: FSMContext) -> None:
    """Выбор даты и показ времени."""
    _, date_str = callback.data.split(":", maxsplit=1)
    chosen_date = date.fromisoformat(date_str)
    times_rows = await db.get_available_times(chosen_date)
    if not times_rows:
        await callback.answer("На этот день нет свободного времени.", show_alert=True)
        return

    await state.update_data(chosen_date=date_str)
    times = [(row["id"], row["time"]) for row in times_rows]
    await state.set_state(BookingStates.choosing_time)
    await safe_edit_text(
        callback,
        f"<b>Дата:</b> {chosen_date.strftime('%d.%m.%Y')}\n\n"
        "<b>Выберите время:</b>",
        reply_markup=booking_times_keyboard(date_str, times),
    )


@router.callback_query(BookingStates.choosing_time, F.data == "back_to_days")
async def back_to_days(callback: CallbackQuery, state: FSMContext) -> None:
    """Возврат к выбору даты."""
    days = await db.get_available_days()
    if not days:
        await state.clear()
        await safe_edit_text(
            callback,
            "К сожалению, сейчас нет доступных слотов для записи.\n"
            "Попробуйте позже.",
            reply_markup=main_menu_keyboard(
                is_admin=callback.from_user.id == config.admin_id
            ),
        )
        return

    await state.set_state(BookingStates.choosing_date)
    await safe_edit_text(
        callback,
        "<b>Выберите дату</b> для записи:",
        reply_markup=booking_days_keyboard(days),
    )


@router.callback_query(BookingStates.choosing_time, F.data.startswith("book_time:"))
async def choose_time(callback: CallbackQuery, state: FSMContext) -> None:
    """Сохраняем слот, затем спрашиваем имя."""
    _, slot_id_str = callback.data.split(":", maxsplit=1)
    slot_id = int(slot_id_str)

    await state.update_data(chosen_slot_id=slot_id)
    await state.set_state(BookingStates.entering_name)
    await safe_edit_text(
        callback,
        "Введите, пожалуйста, ваше <b>имя</b>:",
    )


@router.message(BookingStates.entering_name)
async def enter_name(message: Message, state: FSMContext) -> None:
    """Получаем имя, просим телефон."""
    name = message.text.strip()
    await state.update_data(name=name)
    await state.set_state(BookingStates.entering_phone)
    await message.answer(
        "Теперь отправьте, пожалуйста, ваш <b>номер телефона</b> (в любом удобном формате):"
    )


@router.message(BookingStates.entering_phone)
async def enter_phone(message: Message, state: FSMContext) -> None:
    """Получаем телефон, просим подтвердить запись."""
    phone = message.text.strip()
    await state.update_data(phone=phone)
    data = await state.get_data()

    text = (
        "<b>Проверьте данные записи:</b>\n\n"
        f"Имя: <b>{data.get('name')}</b>\n"
        f"Телефон: <b>{phone}</b>\n"
        "<i>Дата и время будут закреплены после подтверждения.</i>"
    )
    await state.set_state(BookingStates.confirming)
    await message.answer(text, reply_markup=confirm_booking_keyboard())


@router.callback_query(BookingStates.confirming, F.data == "cancel_booking_flow")
async def cancel_booking_flow(callback: CallbackQuery, state: FSMContext) -> None:
    """Отмена процесса записи до подтверждения."""
    await state.clear()
    await safe_edit_text(
        callback,
        "Процесс записи отменён.",
        reply_markup=main_menu_keyboard(
            is_admin=callback.from_user.id == config.admin_id
        ),
    )


async def schedule_reminder(
    scheduler,
    booking_id: int,
    user_tg_id: int,
    date_str: str,
    time_str: str,
    bot,
) -> None:
    """Постановка задачи напоминания за 24 часа."""
    dt_slot = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    run_at = dt_slot - timedelta(hours=24)
    now = datetime.now()
    if run_at <= now:
        # Если запись меньше чем за 24 часа — напоминание не создаём.
        return

    job_id = f"reminder_{booking_id}"

    async def send_reminder():
        try:
            await bot.send_message(
                user_tg_id,
                f"Напоминаем, что вы записаны на наращивание ресниц завтра в {time_str}.\n"
                "Ждём вас 💖",
            )
        except Exception:
            pass

    scheduler.add_job(
        send_reminder,
        "date",
        run_date=run_at,
        id=job_id,
        replace_existing=True,
    )
    await db.save_reminder(booking_id, run_at, job_id)


@router.callback_query(BookingStates.confirming, F.data == "confirm_booking")
async def confirm_booking(callback: CallbackQuery, state: FSMContext, bot, scheduler) -> None:
    """Финальное подтверждение: создаём запись, шлём уведомления, планируем напоминание."""
    data = await state.get_data()
    slot_id = data.get("chosen_slot_id")
    name = data.get("name")
    phone = data.get("phone")

    if slot_id is None:
        await callback.answer("Слот не найден, начните заново.", show_alert=True)
        await state.clear()
        return

    # Сохраняем имя/телефон
    await db.update_user_info(callback.from_user.id, name, phone)

    # Пытаемся забронировать слот
    booking_id = await db.book_slot(callback.from_user.id, slot_id)
    if booking_id is None:
        await safe_edit_text(
            callback,
            "Не удалось создать запись. Возможно, у вас уже есть активная запись "
            "или слот был только что занят.",
            reply_markup=main_menu_keyboard(
                is_admin=callback.from_user.id == config.admin_id
            ),
        )
        await state.clear()
        return

    # Получаем дату и время слота
    slot = await db.get_slot(slot_id)
    if not slot:
        await safe_edit_text(
            callback,
            "Не удалось найти слот после бронирования. Свяжитесь, пожалуйста, с мастером.",
            reply_markup=main_menu_keyboard(
                is_admin=callback.from_user.id == config.admin_id
            ),
        )
        await state.clear()
        return

    date_str = slot["date"]
    time_str = slot["time"]

    # Планируем напоминание
    await schedule_reminder(
        scheduler=scheduler,
        booking_id=booking_id,
        user_tg_id=callback.from_user.id,
        date_str=date_str,
        time_str=time_str,
        bot=bot,
    )

    # Сообщение пользователю
    dt = date.fromisoformat(date_str)
    text = (
        "<b>Запись успешно создана!</b>\n\n"
        f"Дата: <b>{dt.strftime('%d.%m.%Y')}</b>\n"
        f"Время: <b>{time_str}</b>\n"
        f"Имя: <b>{name}</b>\n"
        f"Телефон: <b>{phone}</b>\n\n"
        "До встречи!"
    )
    await safe_edit_text(
        callback,
        text,
        reply_markup=main_menu_keyboard(
            is_admin=callback.from_user.id == config.admin_id
        ),
    )

    # Сообщение админу
    try:
        await bot.send_message(
            config.admin_id,
            f"<b>Новая запись</b>\n\n"
            f"Клиент: <b>{name}</b>\n"
            f"Телефон: <b>{phone}</b>\n"
            f"TG: @{callback.from_user.username or 'без username'}\n"
            f"Дата: <b>{dt.strftime('%d.%m.%Y')}</b>\n"
            f"Время: <b>{time_str}</b>",
        )
    except Exception:
        pass

    # Сообщение в канал с расписанием
    try:
        await bot.send_message(
            config.channel_id,
            f"<b>Запись подтверждена</b>\n"
            f"Дата: <b>{dt.strftime('%d.%m.%Y')}</b>\n"
            f"Время: <b>{time_str}</b>\n"
            f"Клиент: <b>{name}</b>",
        )
    except Exception:
        pass

    await state.clear()


@router.callback_query(F.data == "menu_my_booking")
async def my_booking(callback: CallbackQuery, state: FSMContext) -> None:
    """Показать текущую запись и дать возможность отменить."""
    await state.clear()
    booking = await db.get_active_booking_by_tg(callback.from_user.id)
    if not booking:
        await safe_edit_text(
            callback,
            "У вас нет активной записи.",
            reply_markup=main_menu_keyboard(
                is_admin=callback.from_user.id == config.admin_id
            ),
        )
        return

    dt = date.fromisoformat(booking["date"])
    time_str = booking["time"]
    text = (
        "<b>Ваша запись:</b>\n\n"
        f"Дата: <b>{dt.strftime('%d.%m.%Y')}</b>\n"
        f"Время: <b>{time_str}</b>\n\n"
        "Если вы не сможете прийти, вы можете отменить запись."
    )
    await safe_edit_text(
        callback,
        text,
        reply_markup=cancel_my_booking_keyboard(booking["id"]),
    )


@router.callback_query(F.data.startswith("user_cancel_booking:"))
async def user_cancel_booking(callback: CallbackQuery, bot, scheduler) -> None:
    """Отмена записи пользователем."""
    _, booking_id_str = callback.data.split(":", maxsplit=1)
    booking_id = int(booking_id_str)

    # Удаляем напоминание
    job_id = await db.delete_reminder(booking_id)
    if job_id:
        try:
            scheduler.remove_job(job_id)
        except Exception:
            pass

    # Освобождаем слот
    res = await db.cancel_booking(booking_id)
    if not res:
        await callback.answer("Запись уже отменена или не найдена.", show_alert=True)
        return

    date_str, time_str = res
    dt = date.fromisoformat(date_str)

    await safe_edit_text(
        callback,
        "Ваша запись была отменена.\n"
        "Надеемся увидеть вас в другой день 💖",
        reply_markup=main_menu_keyboard(
            is_admin=callback.from_user.id == config.admin_id
        ),
    )

    # Сообщение админу
    try:
        await bot.send_message(
            config.admin_id,
            "<b>Запись отменена пользователем</b>\n"
            f"Дата: <b>{dt.strftime('%d.%m.%Y')}</b>\n"
            f"Время: <b>{time_str}</b>\n"
            f"TG: @{callback.from_user.username or 'без username'}",
        )
    except Exception:
        pass

    # Сообщение в канал (отдельно, чтобы не зависеть от отправки админу)
    try:
        await bot.send_message(
            config.channel_id,
            "<b>Запись отменена</b>\n"
            f"Дата: <b>{dt.strftime('%d.%m.%Y')}</b>\n"
            f"Время: <b>{time_str}</b>\n"
            f"Отменил: @{callback.from_user.username or 'без username'}",
        )
    except Exception:
        pass


@router.callback_query(F.data == "menu_admin")
async def admin_menu(callback: CallbackQuery, state: FSMContext) -> None:
    """Вход в админ-панель."""
    if callback.from_user.id != config.admin_id:
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    await state.set_state(AdminStates.choosing_action)
    await safe_edit_text(
        callback,
        "<b>Админ-панель</b>\nВыберите действие:",
        reply_markup=admin_panel_keyboard(),
    )


@router.callback_query(AdminStates.choosing_action, F.data == "admin_add_slots")
async def admin_add_slots(callback: CallbackQuery, state: FSMContext) -> None:
    """Начало добавления слотов: просим дату."""
    if callback.from_user.id != config.admin_id:
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    await state.set_state(AdminStates.adding_day)
    await safe_edit_text(
        callback,
        "Введите дату в формате <b>ДД.ММ.ГГГГ</b>, для которой нужно добавить слоты:",
    )


@router.message(AdminStates.adding_day)
async def admin_add_day_date(message: Message, state: FSMContext) -> None:
    """Получаем дату и просим список времени."""
    if message.from_user.id != config.admin_id:
        await message.answer("Недостаточно прав.")
        return

    try:
        dt = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
    except ValueError:
        await message.answer("Неверный формат даты. Используйте ДД.ММ.ГГГГ.")
        return

    await state.update_data(admin_day=dt.isoformat())
    await state.set_state(AdminStates.adding_time_for_day)
    await message.answer(
        "Отправьте список времён через запятую, например:\n"
        "<code>10:00, 12:30, 15:00</code>"
    )


@router.message(AdminStates.adding_time_for_day)
async def admin_add_times(message: Message, state: FSMContext) -> None:
    """Создаём слоты по введённым временам."""
    if message.from_user.id != config.admin_id:
        await message.answer("Недостаточно прав.")
        return

    data = await state.get_data()
    date_str = data.get("admin_day")
    if not date_str:
        await message.answer("Дата не найдена, начните сначала.")
        await state.clear()
        return

    dt = date.fromisoformat(date_str)
    raw = message.text.replace(" ", "")
    parts = [p for p in raw.split(",") if p]
    created = 0
    for p in parts:
        try:
            tm = datetime.strptime(p, "%H:%M").time()
        except ValueError:
            continue
        await db.create_slot(dt, tm)
        created += 1

    await state.clear()
    await message.answer(
        f"Создано слотов: <b>{created}</b> на дату {dt.strftime('%d.%m.%Y')}.",
        reply_markup=admin_panel_keyboard(),
    )


@router.callback_query(AdminStates.choosing_action, F.data == "admin_close_day")
async def admin_close_day_start(callback: CallbackQuery, state: FSMContext) -> None:
    """Запрос даты для закрытия дня."""
    if callback.from_user.id != config.admin_id:
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    await state.set_state(AdminStates.closing_day_choose)
    await safe_edit_text(
        callback,
        "Введите дату в формате <b>ДД.ММ.ГГГГ</b>, которую нужно полностью закрыть:",
    )


@router.message(AdminStates.closing_day_choose)
async def admin_close_day_finish(message: Message, state: FSMContext) -> None:
    if message.from_user.id != config.admin_id:
        await message.answer("Недостаточно прав.")
        return
    try:
        dt = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
    except ValueError:
        await message.answer("Неверный формат даты. Используйте ДД.ММ.ГГГГ.")
        return

    await db.close_day(dt)
    await state.clear()
    await message.answer(
        f"День {dt.strftime('%d.%m.%Y')} полностью закрыт.",
        reply_markup=admin_panel_keyboard(),
    )


@router.callback_query(AdminStates.choosing_action, F.data == "admin_view_day")
async def admin_view_day_start(callback: CallbackQuery, state: FSMContext) -> None:
    """Просмотр расписания на дату."""
    if callback.from_user.id != config.admin_id:
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    await state.set_state(AdminStates.viewing_day_choose)
    await safe_edit_text(
        callback,
        "Введите дату в формате <b>ДД.ММ.ГГГГ</b>, чтобы посмотреть слоты и записи:",
    )


@router.message(AdminStates.viewing_day_choose)
async def admin_view_day_show(message: Message, state: FSMContext) -> None:
    if message.from_user.id != config.admin_id:
        await message.answer("Недостаточно прав.")
        return

    try:
        dt = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
    except ValueError:
        await message.answer("Неверный формат даты. Используйте ДД.ММ.ГГГГ.")
        return

    # Показываем список слотов (упрощённо через get_available_times, можно расширить при необходимости)
    slots = await db.get_available_times(dt)
    if not slots:
        await message.answer(
            f"На {dt.strftime('%d.%m.%Y')} слотов нет или все заняты.",
            reply_markup=admin_panel_keyboard(),
        )
        await state.clear()
        return

    text = as_marked_section(
        Bold(f"Свободные слоты на {dt.strftime('%d.%m.%Y')}:"),
        *[s["time"] for s in slots],
    ).as_html()
    await state.clear()
    await message.answer(text, reply_markup=admin_panel_keyboard())


@router.callback_query(AdminStates.choosing_action, F.data == "admin_cancel_booking")
async def admin_cancel_booking_start(callback: CallbackQuery, state: FSMContext) -> None:
    """Старт отмены записи клиенту: спрашиваем дату."""
    if callback.from_user.id != config.admin_id:
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    await state.set_state(AdminStates.cancelling_booking_choose_day)
    await safe_edit_text(
        callback,
        "Введите дату в формате <b>ДД.ММ.ГГГГ</b>, на которую нужно посмотреть и отменить запись клиента:",
    )


@router.message(AdminStates.cancelling_booking_choose_day)
async def admin_cancel_booking_choose_day(message: Message, state: FSMContext) -> None:
    """Выбор даты для просмотра записей с возможностью отмены."""
    if message.from_user.id != config.admin_id:
        await message.answer("Недостаточно прав.")
        return

    try:
        dt = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
    except ValueError:
        await message.answer("Неверный формат даты. Используйте ДД.ММ.ГГГГ.")
        return

    bookings = await db.get_bookings_for_day(dt)
    if not bookings:
        await state.clear()
        await message.answer(
            f"На {dt.strftime('%d.%m.%Y')} активных записей нет.",
            reply_markup=admin_panel_keyboard(),
        )
        return

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    buttons = []
    for b in bookings:
        label_name = b["name"] or "Без имени"
        label_phone = b["phone"] or "без телефона"
        text = f"{b['time']} — {label_name} ({label_phone})"
        buttons.append(
            [
                InlineKeyboardButton(
                    text=text,
                    callback_data=f"admin_cancel_booking_select:{b['booking_id']}",
                )
            ]
        )
    buttons.append(
        [
            InlineKeyboardButton(
                text="🔙 В админ-панель", callback_data="menu_admin"
            )
        ]
    )
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    await state.update_data(admin_cancel_day=dt.isoformat())
    await state.set_state(AdminStates.cancelling_booking_choose_booking)
    await message.answer(
        f"Выберите запись на {dt.strftime('%d.%m.%Y')} для отмены:",
        reply_markup=kb,
    )


@router.callback_query(
    AdminStates.cancelling_booking_choose_booking,
    F.data.startswith("admin_cancel_booking_select:"),
)
async def admin_cancel_booking_do(
    callback: CallbackQuery, state: FSMContext, bot, scheduler
) -> None:
    """Фактическая отмена записи админом."""
    if callback.from_user.id != config.admin_id:
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    _, booking_id_str = callback.data.split(":", maxsplit=1)
    booking_id = int(booking_id_str)

    info = await db.get_booking_info(booking_id)
    if not info or info["booking_id"] is None:
        await callback.answer("Запись не найдена или уже отменена.", show_alert=True)
        await state.clear()
        return

    job_id = await db.delete_reminder(booking_id)
    if job_id:
        try:
            scheduler.remove_job(job_id)
        except Exception:
            pass

    res = await db.cancel_booking(booking_id)
    if not res:
        await callback.answer("Запись уже отменена или не найдена.", show_alert=True)
        await state.clear()
        return

    date_str, time_str = res
    dt = date.fromisoformat(date_str)

    user_tg_id = info["tg_id"]
    try:
        if user_tg_id:
            await bot.send_message(
                user_tg_id,
                f"Ваша запись на {dt.strftime('%d.%m.%Y')} в {time_str} была "
                f"отменена администратором.\nЕсли нужно, вы можете записаться снова.",
            )
    except Exception:
        pass

    # Сообщение в канал (отдельно, чтобы всегда уходило)
    try:
        await bot.send_message(
            config.channel_id,
            "<b>Запись отменена администратором</b>\n"
            f"Дата: <b>{dt.strftime('%d.%m.%Y')}</b>\n"
            f"Время: <b>{time_str}</b>\n"
            f"Клиент: <b>{info['name'] or 'Без имени'}</b>",
        )
    except Exception:
        pass

    await state.clear()
    await safe_edit_text(
        callback,
        f"Запись клиента на {dt.strftime('%d.%m.%Y')} в {time_str} отменена, слот снова доступен.",
        reply_markup=admin_panel_keyboard(),
    )

