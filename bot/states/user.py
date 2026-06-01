from aiogram.fsm.state import State, StatesGroup


class UserOrderStates(StatesGroup):
    waiting_for_discount_code = State()
    waiting_for_receipt = State()
