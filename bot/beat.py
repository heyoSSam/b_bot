import logging
import os
import tempfile

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bot.audio import add_cover_to_mp3, create_audio_thumbnail
from bot.authors import resolve_authors
from bot.cleanup import add_cleanup_message, answer_and_track, cleanup_messages
from bot.file_names import (
    build_file_name_prompt,
    get_file_name_copy_keyboard,
    get_safe_audio_name,
)
from bot.navigation import get_start_keyboard, with_start_button
from bot.styles import build_track_caption
from bot.subscription import is_user_subscribed, require_subscription
from bot.user_storage import get_user


logger = logging.getLogger(__name__)
router = Router()


class BeatState(StatesGroup):
    waiting_for_audio = State()
    waiting_for_collab_answer = State()
    waiting_for_author_links = State()
    waiting_for_file_name = State()
    waiting_for_cover = State()


def get_collab_keyboard() -> InlineKeyboardMarkup:
    return with_start_button(
        InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Да", callback_data="beat:collab:yes"),
                    InlineKeyboardButton(text="Нет", callback_data="beat:collab:no"),
                ]
            ]
        )
    )


def get_cover_keyboard() -> InlineKeyboardMarkup:
    return with_start_button(
        InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Без обложки", callback_data="beat:cover:skip")]
            ]
        )
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


async def ask_for_cover(message: Message, state: FSMContext):
    await state.set_state(BeatState.waiting_for_cover)
    await answer_and_track(
        message,
        state,
        "Теперь отправьте обложку или нажмите «Без обложки».",
        reply_markup=get_cover_keyboard(),
    )


async def ask_for_file_name(message: Message, state: FSMContext):
    data = await state.get_data()
    audio_file_name = get_safe_audio_name(data.get("audio_file_name"), "beat.mp3")

    await state.set_state(BeatState.waiting_for_file_name)
    await answer_and_track(
        message,
        state,
        build_file_name_prompt(audio_file_name),
        reply_markup=with_start_button(
            get_file_name_copy_keyboard(
                audio_file_name,
                keep_callback_data="beat:file_name:keep",
            )
        ),
        parse_mode="HTML",
    )


async def accept_beat_audio(message: Message, state: FSMContext, bot: Bot) -> None:
    await add_cleanup_message(state, message)
    mp3_file = get_mp3_file(message)

    if not mp3_file:
        await answer_and_track(
            message,
            state,
            "Пока поддерживаются только mp3-файлы.",
            reply_markup=get_start_keyboard(),
        )
        return

    audio_file_id, audio_file_name = mp3_file
    await state.update_data(
        audio_file_id=audio_file_id,
        audio_file_name=audio_file_name,
    )
    await cleanup_messages(bot, state, message.chat.id)
    await state.set_state(BeatState.waiting_for_collab_answer)
    await answer_and_track(
        message,
        state,
        "Этот бит коллабный?",
        reply_markup=get_collab_keyboard(),
    )


async def build_and_send_beat(
    message: Message,
    state: FSMContext,
    bot: Bot,
    db_session: AsyncSession,
    cover_file_id: str | None,
    telegram_user,
) -> None:
    data = await state.get_data()
    safe_audio_file_name = get_safe_audio_name(data["audio_file_name"], "beat.mp3")

    await answer_and_track(message, state, "Обрабатываю бит...")

    try:
        user = await get_user(db_session, telegram_user.id) if telegram_user else None

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = os.path.join(temp_dir, safe_audio_file_name)
            await bot.download(data["audio_file_id"], destination=audio_path)

            audio_kwargs = {
                "audio": FSInputFile(audio_path, filename=safe_audio_file_name),
                "caption": build_track_caption(
                    message,
                    data.get("authors", []),
                    user=user,
                    telegram_user=telegram_user,
                ),
                "parse_mode": "HTML",
            }

            if cover_file_id:
                cover_path = os.path.join(temp_dir, "cover.jpg")
                thumbnail_path = os.path.join(temp_dir, "thumbnail.jpg")

                await bot.download(cover_file_id, destination=cover_path)
                add_cover_to_mp3(audio_path, cover_path)
                create_audio_thumbnail(cover_path, thumbnail_path)
                audio_kwargs["thumbnail"] = FSInputFile(thumbnail_path, filename="thumbnail.jpg")

            await cleanup_messages(bot, state, message.chat.id)
            await message.answer_audio(**audio_kwargs)
    except Exception:
        logger.exception("Failed to build beat")
        await cleanup_messages(bot, state, message.chat.id)
        await state.clear()
        await message.answer(
            "Не удалось собрать бит. Попробуйте снова через /beat.",
            reply_markup=get_start_keyboard(),
        )
        return

    await state.clear()


@router.message(Command("beat"))
async def start_beat(message: Message, state: FSMContext, bot: Bot):
    await cleanup_messages(bot, state, message.chat.id)
    await state.clear()
    await add_cleanup_message(state, message)

    if not await require_subscription(message, bot, "beat"):
        return

    await state.set_state(BeatState.waiting_for_audio)
    await answer_and_track(
        message,
        state,
        "Отправьте mp3-бит.",
        reply_markup=get_start_keyboard(),
    )


@router.callback_query(F.data == "subscription:check:beat")
async def check_beat_subscription(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not await is_user_subscribed(bot, callback.from_user.id):
        await callback.answer("Подписка не найдена.", show_alert=True)
        return

    await callback.answer()

    if callback.message:
        await cleanup_messages(bot, state, callback.message.chat.id)
        await callback.message.edit_reply_markup(reply_markup=None)
        await state.clear()
        await add_cleanup_message(state, callback.message)
        await state.set_state(BeatState.waiting_for_audio)
        await answer_and_track(
            callback.message,
            state,
            "Подписка подтверждена. Отправьте mp3-бит.",
            reply_markup=get_start_keyboard(),
        )


@router.message(StateFilter(None), has_mp3_file)
async def direct_beat_audio_handler(message: Message, state: FSMContext, bot: Bot):
    await cleanup_messages(bot, state, message.chat.id)
    await state.clear()
    await add_cleanup_message(state, message)

    if not await require_subscription(message, bot, "beat"):
        return

    await accept_beat_audio(message, state, bot)


@router.message(BeatState.waiting_for_audio, has_audio_file)
async def beat_audio_handler(message: Message, state: FSMContext, bot: Bot):
    await accept_beat_audio(message, state, bot)


@router.message(BeatState.waiting_for_audio, is_not_command)
async def wrong_beat_audio_handler(message: Message, state: FSMContext):
    await add_cleanup_message(state, message)
    await answer_and_track(
        message,
        state,
        "Сейчас нужно отправить mp3-бит.",
        reply_markup=get_start_keyboard(),
    )


@router.callback_query(BeatState.waiting_for_collab_answer, F.data == "beat:collab:yes")
async def beat_collab_yes_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    await add_cleanup_message(state, callback.message)

    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        await cleanup_messages(bot, state, callback.message.chat.id)
        await state.set_state(BeatState.waiting_for_author_links)
        await answer_and_track(
            callback.message,
            state,
            "Отправьте ссылки на авторов через пробел, запятую или с новой строки.",
            reply_markup=get_start_keyboard(),
        )


@router.callback_query(BeatState.waiting_for_collab_answer, F.data == "beat:collab:no")
async def beat_collab_no_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    await add_cleanup_message(state, callback.message)
    await state.update_data(authors=[])

    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        await cleanup_messages(bot, state, callback.message.chat.id)
        await ask_for_file_name(callback.message, state)


@router.message(BeatState.waiting_for_author_links, F.text)
async def beat_author_links_handler(message: Message, state: FSMContext, bot: Bot):
    await add_cleanup_message(state, message)
    authors = await resolve_authors(bot, message.text)

    if not authors:
        await answer_and_track(
            message,
            state,
            "Отправьте хотя бы одну ссылку: https://..., t.me/... или @username.",
            reply_markup=get_start_keyboard(),
        )
        return

    await state.update_data(authors=authors)
    await cleanup_messages(bot, state, message.chat.id)
    await ask_for_file_name(message, state)


@router.message(BeatState.waiting_for_author_links, is_not_command)
async def wrong_beat_author_links_handler(message: Message, state: FSMContext):
    await add_cleanup_message(state, message)
    await answer_and_track(
        message,
        state,
        "Сейчас нужно отправить ссылки на авторов.",
        reply_markup=get_start_keyboard(),
    )


@router.message(BeatState.waiting_for_file_name, F.text, is_not_command)
async def beat_file_name_handler(message: Message, state: FSMContext, bot: Bot):
    await add_cleanup_message(state, message)
    file_name = message.text.strip()

    if not file_name:
        await answer_and_track(
            message,
            state,
            "Отправьте новое название файла текстом.",
            reply_markup=get_start_keyboard(),
        )
        return

    await state.update_data(audio_file_name=file_name)
    await cleanup_messages(bot, state, message.chat.id)
    await ask_for_cover(message, state)


@router.callback_query(BeatState.waiting_for_file_name, F.data == "beat:file_name:keep")
async def beat_keep_file_name_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    await add_cleanup_message(state, callback.message)

    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        await cleanup_messages(bot, state, callback.message.chat.id)
        await ask_for_cover(callback.message, state)


@router.message(BeatState.waiting_for_file_name, is_not_command)
async def wrong_beat_file_name_handler(message: Message, state: FSMContext):
    await add_cleanup_message(state, message)
    await answer_and_track(
        message,
        state,
        "Сейчас нужно отправить новое название файла текстом.",
        reply_markup=get_start_keyboard(),
    )


@router.message(BeatState.waiting_for_cover, F.photo)
@router.message(BeatState.waiting_for_cover, F.document)
async def beat_cover_handler(
    message: Message,
    state: FSMContext,
    bot: Bot,
    db_session: AsyncSession,
):
    await add_cleanup_message(state, message)
    cover_file_id = get_cover_file_id(message)

    if not cover_file_id:
        await answer_and_track(
            message,
            state,
            "Отправьте обложку как фото/файл JPEG/PNG или нажмите «Без обложки».",
            reply_markup=get_start_keyboard(),
        )
        return

    await build_and_send_beat(message, state, bot, db_session, cover_file_id, message.from_user)


@router.callback_query(BeatState.waiting_for_cover, F.data == "beat:cover:skip")
async def beat_skip_cover_handler(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    db_session: AsyncSession,
):
    await callback.answer()
    await add_cleanup_message(state, callback.message)

    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        await build_and_send_beat(callback.message, state, bot, db_session, None, callback.from_user)


@router.message(BeatState.waiting_for_cover, is_not_command)
async def wrong_beat_cover_handler(message: Message, state: FSMContext):
    await add_cleanup_message(state, message)
    await answer_and_track(
        message,
        state,
        "Сейчас нужно отправить обложку как фото/файл JPEG/PNG или нажать «Без обложки».",
        reply_markup=get_start_keyboard(),
    )
