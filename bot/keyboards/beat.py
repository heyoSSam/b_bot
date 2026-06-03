from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.keyboards.common import with_start_button


def with_beat_back_button(reply_markup: InlineKeyboardMarkup | None = None) -> InlineKeyboardMarkup:
    inline_keyboard = []

    if reply_markup:
        inline_keyboard.extend(reply_markup.inline_keyboard)

    inline_keyboard.append(
        [
            InlineKeyboardButton(
                text="Вернуться к биту",
                callback_data="beat:menu",
            )
        ]
    )

    return with_start_button(InlineKeyboardMarkup(inline_keyboard=inline_keyboard))


def get_collab_keyboard() -> InlineKeyboardMarkup:
    return with_beat_back_button(
        InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Да", callback_data="beat:collab:yes"),
                    InlineKeyboardButton(text="Нет", callback_data="beat:collab:no"),
                ]
            ]
        )
    )


def get_beat_menu_keyboard(has_cover: bool) -> InlineKeyboardMarkup:
    cover_button_text = "Заменить обложку" if has_cover else "Добавить обложку"
    return with_start_button(
        InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Собрать сейчас", callback_data="beat:build")],
                [
                    InlineKeyboardButton(text="Переименовать", callback_data="beat:file_name"),
                    InlineKeyboardButton(text="Соавторы", callback_data="beat:authors"),
                ],
                [InlineKeyboardButton(text=cover_button_text, callback_data="beat:cover")],
            ]
        )
    )


def get_cover_keyboard() -> InlineKeyboardMarkup:
    return with_beat_back_button(
        InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Без обложки", callback_data="beat:cover:skip")]
            ]
        )
    )
