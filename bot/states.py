from aiogram.fsm.state import State, StatesGroup


class Booking(StatesGroup):
    service = State()
    day = State()
    time = State()
    name = State()
    phone = State()
    confirm = State()
