from aiogram.fsm.state import StatesGroup, State


class BookingStates(StatesGroup):
    """FSM для записи клиента."""

    choosing_procedure = State()
    choosing_doctor = State()
    choosing_date = State()
    choosing_time = State()
    entering_name = State()
    entering_phone = State()
    confirming = State()


class AdminStates(StatesGroup):
    """FSM для админ-панели."""

    choosing_action = State()
    adding_procedure = State()
    adding_doctor = State()
    adding_day = State()
    adding_time_for_day = State()
    closing_day_choose = State()
    viewing_day_choose = State()
    cancelling_booking_choose_day = State()
    cancelling_booking_choose_booking = State()
    cleaning_slots_choose = State()
    cleaning_slots_confirm = State()

