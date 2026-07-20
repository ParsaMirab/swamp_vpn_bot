from aiogram.fsm.state import State, StatesGroup


class JoinRequireStates(StatesGroup):
    waiting_for_channel = State()


class ServiceStates(StatesGroup):
    waiting_for_name = State()


class PlanStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_price = State()
    waiting_for_inbound_id = State()
    waiting_for_protocol = State()
    waiting_for_inbound_port = State()
    waiting_for_traffic_limit = State()
    waiting_for_duration_days = State()


class BankCardStates(StatesGroup):
    waiting_for_card_number = State()
    waiting_for_owner_name = State()


class DiscountCodeStates(StatesGroup):
    waiting_for_code = State()
    waiting_for_usage_limit = State()
    waiting_for_per_user_usage_limit = State()
    waiting_for_expiration_days = State()
    waiting_for_discount_amount = State()


class AdminOrderStates(StatesGroup):
    waiting_for_sub_link = State()
    waiting_for_config = State()
    waiting_for_search_order_id = State()


class BroadcastStates(StatesGroup):
    waiting_for_message = State()


class RechargePackageStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_amount = State()


class InboundStates(StatesGroup):
    waiting_for_protocol = State()
    waiting_for_port = State()
    waiting_for_remark = State()
    waiting_for_network = State()
    waiting_for_security = State()
    waiting_for_total_gb = State()
    waiting_for_expire_days = State()


class GiveMoneyStates(StatesGroup):
    waiting_for_username = State()
    waiting_for_amount = State()
