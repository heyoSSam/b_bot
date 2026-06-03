import html
import os

from aiogram.types import CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup

from bot.constants import FILE_NAME_RENAME_PROMPT_TEXT


def get_safe_audio_name(file_name: str | None, default_name: str) -> str:
    safe_name = os.path.basename((file_name or "").strip()) or default_name

    if not safe_name.lower().endswith(".mp3"):
        return f"{safe_name}.mp3"

    return safe_name


def build_file_name_prompt(file_name: str) -> str:
    return FILE_NAME_RENAME_PROMPT_TEXT.format(file_name=html.escape(file_name))


def get_file_name_copy_keyboard(
    file_name: str,
    keep_callback_data: str | None = None,
) -> InlineKeyboardMarkup:
    keyboard = []

    if keep_callback_data:
        keyboard.append(
            [
                InlineKeyboardButton(
                    text="Оставить это название",
                    callback_data=keep_callback_data,
                )
            ]
        )

    keyboard.append(
        [
            InlineKeyboardButton(
                text=file_name,
                copy_text=CopyTextButton(text=file_name),
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=keyboard
    )
