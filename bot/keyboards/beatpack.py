from aiogram.types import CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup

from bot.keyboards.common import with_start_button
from bot.utils.file_names import get_safe_audio_name


def get_recent_authors_keyboard(authors: list[dict[str, str]]) -> InlineKeyboardMarkup | None:
    if not authors:
        return None

    inline_keyboard = []
    row = []

    for author in authors:
        row.append(
            InlineKeyboardButton(
                text=author["label"],
                copy_text=CopyTextButton(text=author["url"]),
            )
        )

        if len(row) == 2:
            inline_keyboard.append(row)
            row = []

    if row:
        inline_keyboard.append(row)

    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


def get_collab_keyboard() -> InlineKeyboardMarkup:
    return with_beatpack_back_button(
        InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Да", callback_data="beatpack:collab:yes"),
                    InlineKeyboardButton(text="Нет", callback_data="beatpack:collab:no"),
                ]
            ]
        )
    )


def get_beatpack_menu_keyboard(tracks: list[dict]) -> InlineKeyboardMarkup:
    inline_keyboard = [
        [
            InlineKeyboardButton(
                text=get_safe_audio_name(track.get("file_name"), f"beat_{index}.mp3"),
                callback_data=f"beatpack:edit:{index - 1}",
            )
        ]
        for index, track in enumerate(tracks, start=1)
    ]

    inline_keyboard.append(
        [
            InlineKeyboardButton(text="Добавить биты", callback_data="beatpack:add"),
            InlineKeyboardButton(text="Готово", callback_data="beatpack:done"),
        ]
    )

    return with_start_button(
        InlineKeyboardMarkup(
            inline_keyboard=inline_keyboard
        )
    )


def get_beatpack_track_action_keyboard() -> InlineKeyboardMarkup:
    return with_beatpack_back_button(
        InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Переименовать", callback_data="beatpack:track:file_name"),
                    InlineKeyboardButton(text="Соавторы", callback_data="beatpack:track:authors"),
                ],
                [
                    InlineKeyboardButton(
                        text="Изменить позицию",
                        callback_data="beatpack:track:move",
                    ),
                ],
                [InlineKeyboardButton(text="Удалить", callback_data="beatpack:track:delete")],
            ]
        )
    )


def get_beatpack_track_position_keyboard(tracks_count: int) -> InlineKeyboardMarkup:
    inline_keyboard = []

    for start_index in range(0, tracks_count, 5):
        inline_keyboard.append(
            [
                InlineKeyboardButton(
                    text=str(position),
                    callback_data=f"beatpack:track:position:{position - 1}",
                )
                for position in range(start_index + 1, min(start_index + 6, tracks_count + 1))
            ]
        )

    inline_keyboard.append(
        [
            InlineKeyboardButton(
                text="Вернуться к биту",
                callback_data="beatpack:track:actions",
            )
        ]
    )

    return with_beatpack_back_button(InlineKeyboardMarkup(inline_keyboard=inline_keyboard))


def with_beatpack_back_button(reply_markup: InlineKeyboardMarkup | None = None) -> InlineKeyboardMarkup:
    inline_keyboard = []

    if reply_markup:
        inline_keyboard.extend(reply_markup.inline_keyboard)

    inline_keyboard.append(
        [
            InlineKeyboardButton(
                text="Вернуться к битпаку",
                callback_data="beatpack:menu",
            )
        ]
    )

    return with_start_button(InlineKeyboardMarkup(inline_keyboard=inline_keyboard))


def get_cover_keyboard() -> InlineKeyboardMarkup:
    return with_start_button(
        InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Без обложки", callback_data="beatpack:cover:skip")]
            ]
        )
    )
