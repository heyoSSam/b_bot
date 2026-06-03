from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_style_constructor_keyboard(has_channel: bool = False) -> InlineKeyboardMarkup:
    first_row = [
        InlineKeyboardButton(text="Добавить ЛС", callback_data="settings:style:add_me"),
    ]

    if has_channel:
        first_row.append(
            InlineKeyboardButton(text="Добавить канал", callback_data="settings:style:add_channel")
        )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            first_row,
            [
                InlineKeyboardButton(text="Добавить соавторов", callback_data="settings:style:add_co_author"),
                InlineKeyboardButton(text="Добавить текст", callback_data="settings:style:add_text"),
            ],
            [
                InlineKeyboardButton(text="Предпросмотр", callback_data="settings:style:preview"),
                InlineKeyboardButton(text="Сохранить", callback_data="settings:style:save"),
            ],
            [
                InlineKeyboardButton(text="Отменить шаг", callback_data="settings:style:undo"),
                InlineKeyboardButton(text="Очистить", callback_data="settings:style:clear"),
            ],
            [
                InlineKeyboardButton(text="Ввести шаблон вручную", callback_data="settings:style:manual"),
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
