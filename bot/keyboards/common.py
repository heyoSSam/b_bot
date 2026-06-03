from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def with_start_button(reply_markup: InlineKeyboardMarkup | None = None) -> InlineKeyboardMarkup:
    inline_keyboard = []

    if reply_markup:
        inline_keyboard.extend(reply_markup.inline_keyboard)

    inline_keyboard.append(
        [
            InlineKeyboardButton(
                text="Меню",
                callback_data="navigation:start",
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
