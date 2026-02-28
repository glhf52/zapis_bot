from datetime import date

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Главное меню пользователя."""
    buttons = [
        [
            InlineKeyboardButton(text="📅 Записаться", callback_data="menu_book"),
        ],
        [
            InlineKeyboardButton(text="💰 Прайсы", callback_data="menu_prices"),
        ],
        [
            InlineKeyboardButton(
                text="🏥 Наши Клиники", callback_data="menu_portfolio"
            ),
        ],
        [
            InlineKeyboardButton(text="🗓 Моя запись", callback_data="menu_my_booking"),
        ],
    ]

    if is_admin:
        buttons.append(
            [
                InlineKeyboardButton(
                    text="⚙️ Админ-панель", callback_data="menu_admin"
                )
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def subscription_check_keyboard(channel_link: str) -> InlineKeyboardMarkup:
    """Клавиатура проверки подписки."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔔 Подписаться", url=channel_link
                ),
            ],
            [
                InlineKeyboardButton(
                    text="✅ Проверить подписку",
                    callback_data="check_subscription",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔙 В меню", callback_data="back_to_menu"
                )
            ],
        ]
    )


def portfolio_keyboard() -> InlineKeyboardMarkup:
    """Кнопка для просмотра портфолио + назад в меню."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Смотреть портфолио",
                    url="https://ru.pinterest.com/crystalwithluv/_created/",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔙 В меню", callback_data="back_to_menu"
                )
            ],
        ]
    )


def booking_days_keyboard(available_days: list[str]) -> InlineKeyboardMarkup:
    """Клавиатура с доступными днями (простая версия без полного календаря)."""
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []

    for day_str in available_days:
        d = date.fromisoformat(day_str)
        text = d.strftime("%d.%m")
        row.append(
            InlineKeyboardButton(
                text=text, callback_data=f"book_day:{day_str}"
            )
        )
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append(
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def booking_times_keyboard(
    date_str: str, times: list[tuple[int, str]]
) -> InlineKeyboardMarkup:
    """Клавиатура со временем для выбранной даты."""
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for slot_id, time_str in times:
        row.append(
            InlineKeyboardButton(
                text=time_str, callback_data=f"book_time:{slot_id}"
            )
        )
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append(
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_days")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_booking_keyboard() -> InlineKeyboardMarkup:
    """Подтверждение записи."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить", callback_data="confirm_booking"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отменить", callback_data="cancel_booking_flow"
                )
            ],
        ]
    )


def cancel_my_booking_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для отмены своей записи."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Отменить запись",
                    callback_data=f"user_cancel_booking:{booking_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔙 В меню", callback_data="back_to_menu"
                )
            ],
        ]
    )


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    """Главное меню админ-панели."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Добавить день/слоты", callback_data="admin_add_slots"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Закрыть день", callback_data="admin_close_day"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📋 Расписание на дату",
                    callback_data="admin_view_day",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Отменить запись клиента",
                    callback_data="admin_cancel_booking",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔙 В главное меню", callback_data="back_to_menu"
                )
            ],
        ]
    )

