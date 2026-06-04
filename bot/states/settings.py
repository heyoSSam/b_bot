from aiogram.fsm.state import State, StatesGroup


class SettingsState(StatesGroup):
    waiting_for_channel = State()
    editing_style = State()
    choosing_style_me = State()
    choosing_style_co_author = State()
    waiting_for_style_ai_description = State()
    waiting_for_style = State()
    waiting_for_style_me_text = State()
    waiting_for_style_co_author_text = State()
    waiting_for_style_text = State()
