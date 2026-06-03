import logging

from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State
from aiogram.types import CallbackQuery, Message

from bot.constants import (
    COVER_FILE_TOO_LARGE_TEXT,
    COVER_IMAGE_INVALID_TEXT,
    COVER_IMAGE_TOO_LARGE_TEXT,
    COVER_MAX_FILE_BYTES,
    COVER_MAX_PIXELS,
)
from bot.keyboards.common import with_start_button
from bot.services.audio_service import (
    CoverFileTooLargeError,
    CoverImageInvalidError,
    CoverImageTooLargeError,
)
from bot.services.cleanup_service import add_cleanup_message, answer_and_track, cleanup_messages
from bot.services.subscription_service import is_user_subscribed, require_subscription
from bot.utils.file_names import (
    build_file_name_prompt,
    get_file_name_copy_keyboard,
    get_safe_audio_name,
)


def is_not_command(message: Message) -> bool:
    return not (message.text and message.text.startswith("/"))


def get_mp3_file(message: Message) -> tuple[str, str] | None:
    if message.audio:
        file_name = message.audio.file_name or "beat.mp3"

        if (
            file_name.lower().endswith(".mp3")
            or message.audio.mime_type in ("audio/mpeg", "audio/mp3")
        ):
            return message.audio.file_id, file_name

        return None

    if message.document:
        file_name = message.document.file_name or "beat.mp3"

        if (
            file_name.lower().endswith(".mp3")
            or message.document.mime_type in ("audio/mpeg", "audio/mp3")
        ):
            return message.document.file_id, file_name

    return None


def has_audio_file(message: Message) -> bool:
    return bool(message.audio or message.document)


def has_mp3_file(message: Message) -> bool:
    return get_mp3_file(message) is not None


def get_cover_file_id(message: Message) -> str | None:
    if message.photo:
        return message.photo[-1].file_id

    if message.document and message.document.mime_type in ("image/jpeg", "image/png"):
        return message.document.file_id

    return None


async def ask_for_author_links(
    message: Message,
    state: FSMContext,
    target_state: State,
    reply_markup,
    notice: str | None = None,
    has_recent_authors: bool = False,
) -> None:
    text = "Отправьте ссылки на авторов через пробел, запятую или с новой строки."

    if has_recent_authors:
        text = (
            "Отправьте ссылки на авторов через пробел, запятую или с новой строки. "
            "Ниже есть кнопки с уже использованными соавторами: они копируют ссылку в буфер."
        )

    if notice:
        text = f"{notice}\n\n{text}"

    await state.set_state(target_state)
    await answer_and_track(
        message,
        state,
        text,
        reply_markup=reply_markup,
    )


async def ask_for_cover(
    message: Message,
    state: FSMContext,
    target_state: State,
    text: str,
    reply_markup,
) -> None:
    await state.set_state(target_state)
    await answer_and_track(
        message,
        state,
        text,
        reply_markup=reply_markup,
    )


async def ask_for_file_name(
    message: Message,
    state: FSMContext,
    target_state: State,
    current_file_name: str | None,
    default_name: str,
    back_reply_markup_builder,
    keep_callback_data: str,
) -> None:
    audio_file_name = get_safe_audio_name(current_file_name, default_name)

    await state.set_state(target_state)
    await answer_and_track(
        message,
        state,
        build_file_name_prompt(audio_file_name),
        reply_markup=back_reply_markup_builder(
            get_file_name_copy_keyboard(
                audio_file_name,
                keep_callback_data=keep_callback_data,
            )
        ),
        parse_mode="HTML",
    )


async def start_audio_flow(
    message: Message,
    state: FSMContext,
    bot: Bot,
    command: str,
    target_state: State,
    prompt_text: str,
    reset_data: dict | None = None,
) -> bool:
    await cleanup_messages(bot, state, message.chat.id)
    await state.clear()
    await add_cleanup_message(state, message)

    if not await require_subscription(message, bot, command):
        return False

    if reset_data:
        await state.update_data(**reset_data)

    await state.set_state(target_state)
    await answer_and_track(
        message,
        state,
        prompt_text,
        reply_markup=with_start_button(),
    )
    return True


async def confirm_subscription(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    target_state: State,
    prompt_text: str,
    reset_data: dict | None = None,
) -> bool:
    if not await is_user_subscribed(bot, callback.from_user.id):
        await callback.answer("Подписка не найдена.", show_alert=True)
        return False

    await callback.answer()

    if not callback.message:
        return True

    await cleanup_messages(bot, state, callback.message.chat.id)
    await callback.message.edit_reply_markup(reply_markup=None)
    await state.clear()
    await add_cleanup_message(state, callback.message)

    if reset_data:
        await state.update_data(**reset_data)

    await state.set_state(target_state)
    await answer_and_track(
        callback.message,
        state,
        prompt_text,
        reply_markup=with_start_button(),
    )
    return True


async def handle_build_exception(
    message: Message,
    state: FSMContext,
    bot: Bot,
    error: Exception,
    logger: logging.Logger,
    log_message: str,
    fallback_text: str,
) -> None:
    await cleanup_messages(bot, state, message.chat.id)
    await state.clear()

    if isinstance(error, CoverFileTooLargeError):
        await message.answer(
            COVER_FILE_TOO_LARGE_TEXT.format(
                max_megabytes=COVER_MAX_FILE_BYTES // (1024 * 1024),
            ),
            reply_markup=with_start_button(),
        )
        return

    if isinstance(error, CoverImageTooLargeError):
        await message.answer(
            COVER_IMAGE_TOO_LARGE_TEXT.format(
                max_megapixels=COVER_MAX_PIXELS // 1_000_000,
            ),
            reply_markup=with_start_button(),
        )
        return

    if isinstance(error, CoverImageInvalidError):
        await message.answer(
            COVER_IMAGE_INVALID_TEXT,
            reply_markup=with_start_button(),
        )
        return

    logger.exception(log_message)
    await message.answer(
        fallback_text,
        reply_markup=with_start_button(),
    )
