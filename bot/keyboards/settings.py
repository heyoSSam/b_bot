from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_style_constructor_keyboard(has_channel: bool = False) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Предпросмотр", callback_data="settings:style:preview"),
                InlineKeyboardButton(text="Изменить", callback_data="settings:style:ai"),
            ],
            [
                InlineKeyboardButton(text="Меню", callback_data="navigation:start"),
            ],
        ]
    )


def get_style_me_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Username", callback_data="settings:style:me_username"),
                InlineKeyboardButton(text="Свой текст", callback_data="settings:style:me_custom"),
            ],
            [
                InlineKeyboardButton(text="Назад", callback_data="settings:style:back"),
            ],
            [
                InlineKeyboardButton(text="Меню", callback_data="navigation:start"),
            ],
        ]
    )


def get_style_co_author_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Свой текст", callback_data="settings:style:co_author_custom"),
                InlineKeyboardButton(text="Без текста", callback_data="settings:style:co_author_empty"),
            ],
            [
                InlineKeyboardButton(text="Назад", callback_data="settings:style:back"),
            ],
            [
                InlineKeyboardButton(text="Меню", callback_data="navigation:start"),
            ],
        ]
    )
