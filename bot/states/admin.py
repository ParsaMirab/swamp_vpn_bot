from aiogram.fsm.state import State, StatesGroup


class JoinRequireStates(StatesGroup):
    waiting_for_channel = State()


class ServiceStates(StatesGroup):
    waiting_for_name = State()


class PlanStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_price = State()


class BankCardStates(StatesGroup):
    waiting_for_card_number = State()
    waiting_for_owner_name = State()


class DiscountCodeStates(StatesGroup):
    waiting_for_code = State()
    waiting_for_usage_limit = State()
    waiting_for_discount_amount = State()


class AdminOrderStates(StatesGroup):
    waiting_for_config = State()
    waiting_for_search_order_id = State()
