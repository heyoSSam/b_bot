from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Один бит",
                    callback_data="start:beat",
                ),
                InlineKeyboardButton(
                    text="Битпак",
                    callback_data="start:beatpack",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Мой канал",
                    callback_data="start:set_channel",
                ),
                InlineKeyboardButton(
                    text="Шаблон",
                    callback_data="start:set_style",
                ),
            ],
        ]
    )
