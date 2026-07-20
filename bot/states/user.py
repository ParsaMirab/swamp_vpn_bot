from aiogram.fsm.state import State, StatesGroup


class UserOrderStates(StatesGroup):
    waiting_for_discount_code = State()
    waiting_for_receipt = State()


class UserWalletStates(StatesGroup):
    waiting_for_receipt = State()


class UserCardToCardStates(StatesGroup):
    waiting_for_receipt = State()


class UserWalletPaymentStates(StatesGroup):
    confirming_payment = State()
