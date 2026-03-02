from __future__ import annotations

import os
from datetime import datetime, date, time, timedelta
from pathlib import Path

from aiogram import Router, F
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.utils.formatting import Bold, as_marked_section
from aiogram.exceptions import TelegramBadRequest

from config import config
from storage import db
from keyboards import (
    main_menu_keyboard,
    subscription_check_keyboard,
    booking_procedures_keyboard,
    booking_doctors_keyboard,
    admin_procedures_keyboard,
    admin_doctors_keyboard,
    admin_days_keyboard,
    booking_days_keyboard,
    booking_times_keyboard,
    confirm_booking_keyboard,
    cancel_my_booking_keyboard,
    admin_panel_keyboard,
    portfolio_keyboard,
)
from states import BookingStates, AdminStates


router = Router()
MAIN_MENU_IMAGE_CACHE_FILE = Path(config.database_path).parent / "main_menu_image.txt"

MAIN_MENU_TEXT = (
    "Привет! 👋\n"
    "Добро пожаловать в стоматологию Green Apple! 🍏\n"
    "Я помогу вам быстро и удобно записаться на приём к нашим специалистам.\n"
    "Пожалуйста, выберите удобную дату и время, и мы позаботимся о вашей улыбке! 😁"
)


async def send_main_menu(message: Message, user_id: int) -> None:
    """Показ главного меню с картинкой (если задан MAIN_MENU_IMAGE)."""
    await db.get_or_create_user(user_id)

    # Удаляем предыдущее главное меню, чтобы оставалось только одно
    old_menu_id = await db.get_last_menu_message_id(user_id)
    if old_menu_id:
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=old_menu_id)
        except Exception:
            pass

    is_admin = user_id == config.admin_id
    kb = main_menu_keyboard(is_admin=is_admin)

    db_image = await db.get_setting("main_menu_image")
    cached_image = ""
    if MAIN_MENU_IMAGE_CACHE_FILE.exists():
        try:
            cached_image = MAIN_MENU_IMAGE_CACHE_FILE.read_text(encoding="utf-8").strip()
        except Exception:
            cached_image = ""

    image_source = (db_image or cached_image or config.main_menu_image or "").strip()
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
            sent = await message.answer_photo(photo=photo, caption=MAIN_MENU_TEXT, reply_markup=kb)
            await db.set_last_menu_message_id(user_id, sent.message_id)
            return
        except Exception as e:
            # Если картинка недоступна/путь неверный — показываем обычное меню текстом.
            # Логируем причину для диагностики на хостинге.
            print(f"[MAIN_MENU_IMAGE] send photo failed: {e}", flush=True)

    sent = await message.answer(MAIN_MENU_TEXT, reply_markup=kb)
    await db.set_last_menu_message_id(user_id, sent.message_id)


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


@router.message(StateFilter(None), F.text)
async def ask_to_start(message: Message) -> None:
    """Подсказка для пользователя до старта."""
    if message.text.strip().lower() == "/start":
        return
    await message.answer("Пишите /start чтобы начать.")


@router.message(F.photo)
async def get_photo_file_id(message: Message) -> None:
    """
    Утилита для админа:
    отправьте боту фото, и он вернёт file_id (самый большой размер).
    """
    if message.from_user.id != config.admin_id:
        return
    file_id = message.photo[-1].file_id
    await db.set_setting("main_menu_image", file_id)
    try:
        MAIN_MENU_IMAGE_CACHE_FILE.write_text(file_id, encoding="utf-8")
    except Exception as e:
        print(f"[MAIN_MENU_IMAGE] cache write failed: {e}", flush=True)
    await message.answer(
        "<b>Готово!</b> Картинка главного меню обновлена.\n\n"
        "<b>file_id:</b>\n"
        f"<code>{file_id}</code>\n\n"
        "Теперь отправьте <code>/start</code> и проверьте меню."
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
        "Осмотр — <b>1000₽</b>\n"
        "Лечение Краиеса — <b>5000₽</b>"
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
    """Раздел с адресами клиник (без FSM)."""
    text = (
        "🏥 <b>Стоматология Green Apple — г. Балаково, Саратовская область</b>\n\n"
        "📍 <b>Адреса наших клиник:</b>\n\n"
        "• Ул. Ленина, 122а\n"
        "☎️ +7 937 143-32-22\n\n"
        "• Ул. Свердлова, 58\n"
        "☎️ +7 937 243-32-22\n\n"
        "• Ул. Братьев Захаровых, 154\n"
        "☎️ +7 937 243-32-22\n\n"
        "• Ул. Шевченко, 122\n"
        "☎️ +7 937 145-52-22\n\n"
        "• Ул. Трнавская, 27\n"
        "☎️ +7 909 334-44-43\n\n"
        "🌐 Следите за нами и записывайтесь онлайн: tg -\n\n"
        "Пишите или звоните — мы всегда рады помочь вашей улыбке!"
    )
    await safe_edit_text(callback, text, reply_markup=portfolio_keyboard())


@router.callback_query(F.data == "menu_book")
async def start_booking(callback: CallbackQuery, state: FSMContext, bot) -> None:
    """Начало процесса записи: проверка подписки, затем выбор процедуры."""
    if not await check_subscription(callback.from_user.id, bot):
        await safe_edit_text(
            callback,
            "Для записи необходимо подписаться на канал.",
            reply_markup=subscription_check_keyboard(config.channel_link),
        )
        return

    procedures_rows = await db.get_procedures()
    procedures = [(row["id"], row["name"]) for row in procedures_rows]
    if not procedures:
        await safe_edit_text(
            callback,
            "Пока не настроены процедуры. Обратитесь к администратору.",
            reply_markup=main_menu_keyboard(
                is_admin=callback.from_user.id == config.admin_id
            ),
        )
        return

    await state.set_state(BookingStates.choosing_procedure)
    await safe_edit_text(
        callback,
        "<b>Выберите процедуру:</b>",
        reply_markup=booking_procedures_keyboard(procedures),
    )


@router.callback_query(BookingStates.choosing_procedure, F.data.startswith("book_procedure:"))
async def choose_procedure(callback: CallbackQuery, state: FSMContext) -> None:
    """Выбор процедуры и показ доступных врачей."""
    _, procedure_id_str = callback.data.split(":", maxsplit=1)
    procedure_id = int(procedure_id_str)

    doctors_rows = await db.get_doctors_for_procedure(procedure_id)
    if not doctors_rows:
        await callback.answer("Для этой процедуры пока нет доступных врачей.", show_alert=True)
        return

    await state.update_data(chosen_procedure_id=procedure_id)
    await state.set_state(BookingStates.choosing_doctor)
    doctors = [(row["id"], row["name"]) for row in doctors_rows]
    await safe_edit_text(
        callback,
        "<b>Выберите врача:</b>",
        reply_markup=booking_doctors_keyboard(doctors),
    )


@router.callback_query(BookingStates.choosing_doctor, F.data == "back_to_procedures")
async def back_to_procedures(callback: CallbackQuery, state: FSMContext) -> None:
    """Возврат к выбору процедуры."""
    procedures_rows = await db.get_procedures()
    procedures = [(row["id"], row["name"]) for row in procedures_rows]
    await state.set_state(BookingStates.choosing_procedure)
    await safe_edit_text(
        callback,
        "<b>Выберите процедуру:</b>",
        reply_markup=booking_procedures_keyboard(procedures),
    )


@router.callback_query(BookingStates.choosing_doctor, F.data.startswith("book_doctor:"))
async def choose_doctor(callback: CallbackQuery, state: FSMContext) -> None:
    """Выбор врача и показ доступных дат."""
    _, doctor_id_str = callback.data.split(":", maxsplit=1)
    doctor_id = int(doctor_id_str)
    data = await state.get_data()
    procedure_id = data.get("chosen_procedure_id")
    if not procedure_id:
        await callback.answer("Сначала выберите процедуру.", show_alert=True)
        await state.set_state(BookingStates.choosing_procedure)
        return

    days = await db.get_available_days(procedure_id=procedure_id, doctor_id=doctor_id)
    if not days:
        await safe_edit_text(
            callback,
            "К сожалению, для выбранного врача сейчас нет доступных слотов.\n"
            "Выберите другого врача или попробуйте позже.",
            reply_markup=booking_doctors_keyboard(
                [(row["id"], row["name"]) for row in await db.get_doctors_for_procedure(procedure_id)]
            ),
        )
        return

    await state.update_data(chosen_doctor_id=doctor_id)
    await state.set_state(BookingStates.choosing_date)
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
    data = await state.get_data()
    procedure_id = data.get("chosen_procedure_id")
    doctor_id = data.get("chosen_doctor_id")
    if not procedure_id or not doctor_id:
        await callback.answer("Сначала выберите процедуру и врача.", show_alert=True)
        return
    times_rows = await db.get_available_times(
        chosen_date, procedure_id=procedure_id, doctor_id=doctor_id
    )
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
    data = await state.get_data()
    procedure_id = data.get("chosen_procedure_id")
    doctor_id = data.get("chosen_doctor_id")
    if not procedure_id or not doctor_id:
        await state.set_state(BookingStates.choosing_procedure)
        procedures_rows = await db.get_procedures()
        await safe_edit_text(
            callback,
            "<b>Выберите процедуру:</b>",
            reply_markup=booking_procedures_keyboard(
                [(row["id"], row["name"]) for row in procedures_rows]
            ),
        )
        return
    days = await db.get_available_days(procedure_id=procedure_id, doctor_id=doctor_id)
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


@router.callback_query(BookingStates.choosing_date, F.data == "back_to_doctors")
async def back_to_doctors(callback: CallbackQuery, state: FSMContext) -> None:
    """Возврат к выбору врача."""
    data = await state.get_data()
    procedure_id = data.get("chosen_procedure_id")
    if not procedure_id:
        await state.set_state(BookingStates.choosing_procedure)
        procedures_rows = await db.get_procedures()
        await safe_edit_text(
            callback,
            "<b>Выберите процедуру:</b>",
            reply_markup=booking_procedures_keyboard(
                [(row["id"], row["name"]) for row in procedures_rows]
            ),
        )
        return
    doctors_rows = await db.get_doctors_for_procedure(procedure_id)
    await state.set_state(BookingStates.choosing_doctor)
    await safe_edit_text(
        callback,
        "<b>Выберите врача:</b>",
        reply_markup=booking_doctors_keyboard(
            [(row["id"], row["name"]) for row in doctors_rows]
        ),
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
    """Совместимость: планирует все напоминания для записи."""
    await schedule_booking_reminders(
        scheduler=scheduler,
        booking_id=booking_id,
        user_tg_id=user_tg_id,
        date_str=date_str,
        time_str=time_str,
        bot=bot,
    )


async def schedule_booking_reminders(
    scheduler,
    booking_id: int,
    user_tg_id: int,
    date_str: str,
    time_str: str,
    bot,
) -> None:
    """Постановка напоминаний за 24/4/2 часа до записи."""
    dt_slot = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    now = datetime.now()

    reminders = [
        (24, f"Напоминаем, что вы записаны в стоматологию завтра в {time_str}.\nЖдём вас! 🦷"),
        (4, f"Напоминаем, ваш приём через 4 часа в {time_str}.\nДо встречи! 🦷"),
        (2, f"Напоминаем, ваш приём через 2 часа в {time_str}.\nДо встречи! 🦷"),
    ]

    for hours_before, text in reminders:
        run_at = dt_slot - timedelta(hours=hours_before)
        if run_at <= now:
            continue
        job_id = f"reminder_{booking_id}_{hours_before}h"

        async def send_reminder(reminder_text: str = text):
            try:
                await bot.send_message(user_tg_id, reminder_text)
            except Exception:
                pass

        scheduler.add_job(
            send_reminder,
            "date",
            run_date=run_at,
            id=job_id,
            replace_existing=True,
        )


def remove_booking_reminders(scheduler, booking_id: int) -> None:
    """Удаление всех задач напоминаний для записи."""
    for hours_before in (24, 4, 2):
        job_id = f"reminder_{booking_id}_{hours_before}h"
        try:
            scheduler.remove_job(job_id)
        except Exception:
            pass


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
    doctor_name = slot["doctor_name"] or "Не указан"
    procedure_name = slot["procedure_name"] or "Не указана"

    # Планируем напоминания
    await schedule_booking_reminders(
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
        f"Процедура: <b>{procedure_name}</b>\n"
        f"Врач: <b>{doctor_name}</b>\n"
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
            f"Процедура: <b>{procedure_name}</b>\n"
            f"Врач: <b>{doctor_name}</b>\n"
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
            f"Процедура: <b>{procedure_name}</b>\n"
            f"Врач: <b>{doctor_name}</b>\n"
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
    doctor_name = booking["doctor_name"] or "Не указан"
    procedure_name = booking["procedure_name"] or "Не указана"
    text = (
        "<b>Ваша запись:</b>\n\n"
        f"Процедура: <b>{procedure_name}</b>\n"
        f"Врач: <b>{doctor_name}</b>\n"
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

    # Удаляем напоминания
    remove_booking_reminders(scheduler, booking_id)

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
    """Начало добавления слотов: выбор процедуры через inline."""
    if callback.from_user.id != config.admin_id:
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    procedures_rows = await db.get_procedures()
    procedures = [(row["id"], row["name"]) for row in procedures_rows]
    if not procedures:
        await callback.answer("Справочник процедур пуст.", show_alert=True)
        return

    await state.set_state(AdminStates.adding_procedure)
    await safe_edit_text(
        callback,
        "<b>Добавление слотов</b>\n\nВыберите процедуру:",
        reply_markup=admin_procedures_keyboard(procedures),
    )


@router.callback_query(
    AdminStates.adding_procedure,
    F.data.startswith("admin_add_procedure:"),
)
async def admin_add_select_procedure_cb(callback: CallbackQuery, state: FSMContext) -> None:
    """Выбор процедуры через inline-кнопку."""
    if callback.from_user.id != config.admin_id:
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    _, procedure_id_str = callback.data.split(":", maxsplit=1)
    procedure_id = int(procedure_id_str)
    doctors_rows = await db.get_doctors_for_procedure(procedure_id)
    doctors = [(row["id"], row["name"]) for row in doctors_rows]
    if not doctors:
        await callback.answer("Для выбранной процедуры нет врачей.", show_alert=True)
        return

    await state.update_data(admin_procedure_id=procedure_id)
    await state.set_state(AdminStates.adding_doctor)
    await safe_edit_text(
        callback,
        "<b>Добавление слотов</b>\n\nВыберите врача:",
        reply_markup=admin_doctors_keyboard(doctors),
    )


@router.callback_query(AdminStates.adding_doctor, F.data == "admin_add_back_to_procedures")
async def admin_add_back_to_procedures(callback: CallbackQuery, state: FSMContext) -> None:
    """Возврат к выбору процедуры из выбора врача."""
    if callback.from_user.id != config.admin_id:
        await callback.answer("Недостаточно прав.", show_alert=True)
        return
    procedures_rows = await db.get_procedures()
    procedures = [(row["id"], row["name"]) for row in procedures_rows]
    await state.set_state(AdminStates.adding_procedure)
    await safe_edit_text(
        callback,
        "<b>Добавление слотов</b>\n\nВыберите процедуру:",
        reply_markup=admin_procedures_keyboard(procedures),
    )


@router.callback_query(AdminStates.adding_doctor, F.data.startswith("admin_add_doctor:"))
async def admin_add_select_doctor_cb(callback: CallbackQuery, state: FSMContext) -> None:
    """Выбор врача через inline-кнопку."""
    if callback.from_user.id != config.admin_id:
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    _, doctor_id_str = callback.data.split(":", maxsplit=1)
    doctor_id = int(doctor_id_str)
    data = await state.get_data()
    procedure_id = data.get("admin_procedure_id")
    allowed_doctors = await db.get_doctors_for_procedure(procedure_id)
    allowed_ids = {row["id"] for row in allowed_doctors}
    if doctor_id not in allowed_ids:
        await callback.answer("Этот врач недоступен для процедуры.", show_alert=True)
        return

    await state.update_data(admin_doctor_id=doctor_id)
    await state.set_state(AdminStates.adding_day)
    await safe_edit_text(
        callback,
        "Введите дату в формате <b>ДД.ММ.ГГГГ</b>, для которой нужно добавить слоты:",
    )


@router.message(AdminStates.adding_procedure)
async def admin_add_select_procedure(message: Message, state: FSMContext) -> None:
    """Фолбэк: получаем ID процедуры текстом и просим выбрать врача."""
    if message.from_user.id != config.admin_id:
        await message.answer("Недостаточно прав.")
        return

    try:
        procedure_id = int(message.text.strip())
    except ValueError:
        await message.answer("Введите корректный ID процедуры числом.")
        return

    doctors = await db.get_doctors_for_procedure(procedure_id)
    if not doctors:
        await message.answer("Для выбранной процедуры нет врачей. Введите другой ID.")
        return

    await state.update_data(admin_procedure_id=procedure_id)
    await state.set_state(AdminStates.adding_doctor)
    doctors_text = "\n".join([f"{r['id']}. {r['name']}" for r in doctors])
    await message.answer(
        "Выберите врача. Отправьте ID врача:\n\n"
        f"{doctors_text}"
    )


@router.message(AdminStates.adding_doctor)
async def admin_add_select_doctor(message: Message, state: FSMContext) -> None:
    """Фолбэк: получаем врача текстом и просим дату."""
    if message.from_user.id != config.admin_id:
        await message.answer("Недостаточно прав.")
        return
    try:
        doctor_id = int(message.text.strip())
    except ValueError:
        await message.answer("Введите корректный ID врача числом.")
        return

    data = await state.get_data()
    procedure_id = data.get("admin_procedure_id")
    allowed_doctors = await db.get_doctors_for_procedure(procedure_id)
    allowed_ids = {row["id"] for row in allowed_doctors}
    if doctor_id not in allowed_ids:
        await message.answer("Этот врач не привязан к выбранной процедуре. Введите другой ID.")
        return

    await state.update_data(admin_doctor_id=doctor_id)
    await state.set_state(AdminStates.adding_day)
    await message.answer("Введите дату в формате <b>ДД.ММ.ГГГГ</b>, для которой нужно добавить слоты:")


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
    doctor_id = data.get("admin_doctor_id")
    procedure_id = data.get("admin_procedure_id")
    if not date_str or not doctor_id or not procedure_id:
        await message.answer("Не хватает данных (процедура/врач/дата). Начните сначала.")
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
        await db.create_slot(dt, tm, doctor_id=doctor_id, procedure_id=procedure_id)
        created += 1

    await state.clear()
    await message.answer(
        f"Создано слотов: <b>{created}</b> на дату {dt.strftime('%d.%m.%Y')}.",
        reply_markup=admin_panel_keyboard(),
    )


@router.callback_query(AdminStates.choosing_action, F.data == "admin_close_day")
async def admin_close_day_start(callback: CallbackQuery, state: FSMContext) -> None:
    """Выбор даты кнопками для закрытия дня."""
    if callback.from_user.id != config.admin_id:
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    days = await db.get_slot_days()
    if not days:
        await callback.answer("Нет дней со слотами для закрытия.", show_alert=True)
        return

    await state.set_state(AdminStates.closing_day_choose)
    await safe_edit_text(
        callback,
        "<b>Выберите день</b>, который нужно полностью закрыть:",
        reply_markup=admin_days_keyboard(days, prefix="admin_close_day_pick"),
    )


@router.callback_query(
    AdminStates.closing_day_choose, F.data.startswith("admin_close_day_pick:")
)
async def admin_close_day_finish(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id != config.admin_id:
        await callback.answer("Недостаточно прав.", show_alert=True)
        return
    try:
        _, date_str = callback.data.split(":", maxsplit=1)
        dt = date.fromisoformat(date_str)
    except ValueError:
        await callback.answer("Ошибка даты.", show_alert=True)
        return

    await db.close_day(dt)
    await state.clear()
    await safe_edit_text(
        callback,
        f"День {dt.strftime('%d.%m.%Y')} полностью закрыт.",
        reply_markup=admin_panel_keyboard(),
    )


@router.callback_query(AdminStates.choosing_action, F.data == "admin_view_day")
async def admin_view_day_start(callback: CallbackQuery, state: FSMContext) -> None:
    """Выбор даты кнопками для просмотра расписания."""
    if callback.from_user.id != config.admin_id:
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    days = await db.get_slot_days()
    if not days:
        await callback.answer("Пока нет слотов для просмотра расписания.", show_alert=True)
        return

    await state.set_state(AdminStates.viewing_day_choose)
    await safe_edit_text(
        callback,
        "<b>Выберите дату</b>, чтобы посмотреть расписание:",
        reply_markup=admin_days_keyboard(days, prefix="admin_view_day_pick"),
    )


@router.callback_query(
    AdminStates.viewing_day_choose, F.data.startswith("admin_view_day_pick:")
)
async def admin_view_day_show(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id != config.admin_id:
        await callback.answer("Недостаточно прав.", show_alert=True)
        return

    try:
        _, date_str = callback.data.split(":", maxsplit=1)
        dt = date.fromisoformat(date_str)
    except ValueError:
        await callback.answer("Ошибка даты.", show_alert=True)
        return

    rows = await db.get_day_schedule(dt)
    if not rows:
        await state.clear()
        await safe_edit_text(
            callback,
            f"На {dt.strftime('%d.%m.%Y')} расписания нет.",
            reply_markup=admin_panel_keyboard(),
        )
        return

    lines = []
    for row in rows:
        doctor = row["doctor_name"] or "Без врача"
        procedure = row["procedure_name"] or "Без процедуры"
        if row["booking_id"]:
            client = row["client_name"] or "Без имени"
            phone = row["client_phone"] or "без телефона"
            status = f"🔴 Занято ({client}, {phone})"
        else:
            status = "🟢 Свободно"
        lines.append(f"{row['time']} — {procedure}, {doctor}\n{status}")

    text = as_marked_section(
        Bold(f"Расписание на {dt.strftime('%d.%m.%Y')}:"), *lines
    ).as_html()
    await state.clear()
    await safe_edit_text(callback, text, reply_markup=admin_panel_keyboard())


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

    remove_booking_reminders(scheduler, booking_id)

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

