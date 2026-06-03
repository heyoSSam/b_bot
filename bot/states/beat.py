from aiogram.fsm.state import State, StatesGroup


class BeatState(StatesGroup):
    waiting_for_audio = State()
    choosing_next_step = State()
    waiting_for_collab_answer = State()
    waiting_for_author_links = State()
    waiting_for_file_name = State()
    waiting_for_cover = State()
