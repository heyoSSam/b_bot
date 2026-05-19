import logging
import os
import tempfile

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaAudio,
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


class BeatpackState(StatesGroup):
    waiting_for_audio = State()
    waiting_for_collab_answer = State()
    waiting_for_author_links = State()
    waiting_for_file_name = State()
    choosing_next_step = State()
    waiting_for_cover = State()


def get_collab_keyboard() -> InlineKeyboardMarkup:
    return with_start_button(
        InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Да", callback_data="beatpack:collab:yes"),
                    InlineKeyboardButton(text="Нет", callback_data="beatpack:collab:no"),
                ]
            ]
        )
    )


def get_next_step_keyboard() -> InlineKeyboardMarkup:
    return with_start_button(
        InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Добавить ещё бит", callback_data="beatpack:add"),
                    InlineKeyboardButton(text="Готово", callback_data="beatpack:done"),
                ]
            ]
        )
    )


def get_cover_keyboard() -> InlineKeyboardMarkup:
    return with_start_button(
        InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Без обложки", callback_data="beatpack:cover:skip")]
            ]
        )
    )


async def save_pending_track(state: FSMContext) -> int:
    data = await state.get_data()
    tracks = list(data.get("tracks", []))

    tracks.append(
        {
            "file_id": data["pending_audio_file_id"],
            "file_name": data["pending_audio_file_name"],
            "authors": data.get("pending_authors") or [],
        }
    )

    await state.update_data(
        tracks=tracks,
        pending_audio_file_id=None,
        pending_audio_file_name=None,
        pending_authors=None,
    )

    return len(tracks)


def split_media(media: list[InputMediaAudio]) -> list[list[InputMediaAudio]]:
    return [media[index : index + 10] for index in range(0, len(media), 10)]


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


def get_cover_file_id(message: Message) -> str | None:
    if message.photo:
        return message.photo[-1].file_id

    if message.document and message.document.mime_type in ("image/jpeg", "image/png"):
        return message.document.file_id

    return None


async def ask_for_file_name(message: Message, state: FSMContext):
    data = await state.get_data()
    audio_file_name = get_safe_audio_name(data.get("pending_audio_file_name"), "beat.mp3")

    await state.set_state(BeatpackState.waiting_for_file_name)
    await answer_and_track(
        message,
        state,
        build_file_name_prompt(audio_file_name),
        reply_markup=with_start_button(
            get_file_name_copy_keyboard(
                audio_file_name,
                keep_callback_data="beatpack:file_name:keep",
            )
        ),
        parse_mode="HTML",
    )


async def ask_for_cover(message: Message, state: FSMContext):
    await state.set_state(BeatpackState.waiting_for_cover)
    await answer_and_track(
        message,
        state,
        "Теперь отправьте обложку для битпака или нажмите «Без обложки».",
        reply_markup=get_cover_keyboard(),
    )


async def build_and_send_beatpack(
    message: Message,
    state: FSMContext,
    bot: Bot,
    db_session: AsyncSession,
    cover_file_id: str | None,
    telegram_user,
) -> None:
    data = await state.get_data()
    tracks = data.get("tracks", [])

    if not tracks:
        await cleanup_messages(bot, state, message.chat.id)
        await state.clear()
        await message.answer(
            "Битпак пустой. Начните заново через /beatpack.",
            reply_markup=get_start_keyboard(),
        )
        return

    await answer_and_track(message, state, f"Обрабатываю битпак. Битов: {len(tracks)}.")

    try:
        user = await get_user(db_session, telegram_user.id) if telegram_user else None

        with tempfile.TemporaryDirectory() as temp_dir:
            media = []
            cover_path = None
            thumbnail_path = None

            if cover_file_id:
                cover_path = os.path.join(temp_dir, "cover.jpg")
                thumbnail_path = os.path.join(temp_dir, "thumbnail.jpg")
                await bot.download(cover_file_id, destination=cover_path)
                create_audio_thumbnail(cover_path, thumbnail_path)

            for index, track in enumerate(tracks, start=1):
                safe_name = get_safe_audio_name(track["file_name"], f"beat_{index}.mp3")
                audio_path = os.path.join(temp_dir, f"{index}_{safe_name}")

                await bot.download(track["file_id"], destination=audio_path)

                media_kwargs = {
                    "media": FSInputFile(audio_path, filename=safe_name),
                    "caption": build_track_caption(
                        message,
                        track.get("authors", []),
                        user=user,
                        telegram_user=telegram_user,
                    ),
                    "parse_mode": "HTML",
                }

                if cover_path and thumbnail_path:
                    add_cover_to_mp3(audio_path, cover_path)
                    media_kwargs["thumbnail"] = FSInputFile(
                        thumbnail_path,
                        filename=f"thumbnail_{index}.jpg",
                    )

                media.append(InputMediaAudio(**media_kwargs))

            if len(media) == 1:
                audio_kwargs = {
                    "audio": media[0].media,
                    "caption": media[0].caption,
                    "parse_mode": "HTML",
                }

                if media[0].thumbnail:
                    audio_kwargs["thumbnail"] = media[0].thumbnail

                await cleanup_messages(bot, state, message.chat.id)
                await message.answer_audio(**audio_kwargs)
            else:
                await cleanup_messages(bot, state, message.chat.id)
                for media_group in split_media(media):
                    await bot.send_media_group(chat_id=message.chat.id, media=media_group)
    except Exception:
        logger.exception("Failed to build beatpack")
        await cleanup_messages(bot, state, message.chat.id)
        await state.clear()
        await message.answer(
            "Не удалось собрать битпак. Попробуйте снова через /beatpack.",
            reply_markup=get_start_keyboard(),
        )
        return

    await state.clear()


@router.message(Command("beatpack"))
async def start_beatpack(message: Message, state: FSMContext, bot: Bot):
    await cleanup_messages(bot, state, message.chat.id)
    await state.clear()
    await add_cleanup_message(state, message)

    if not await require_subscription(message, bot, "beatpack"):
        return

    await state.update_data(tracks=[])
    await state.set_state(BeatpackState.waiting_for_audio)
    await answer_and_track(
        message,
        state,
        "Отправьте первый mp3-бит для битпака.",
        reply_markup=get_start_keyboard(),
    )


@router.callback_query(F.data == "subscription:check:beatpack")
async def check_beatpack_subscription(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not await is_user_subscribed(bot, callback.from_user.id):
        await callback.answer("Подписка не найдена.", show_alert=True)
        return

    await callback.answer()

    if callback.message:
        await cleanup_messages(bot, state, callback.message.chat.id)
        await callback.message.edit_reply_markup(reply_markup=None)
        await state.clear()
        await add_cleanup_message(state, callback.message)
        await state.update_data(tracks=[])
        await state.set_state(BeatpackState.waiting_for_audio)
        await answer_and_track(
            callback.message,
            state,
            "Подписка подтверждена. Отправьте первый mp3-бит.",
            reply_markup=get_start_keyboard(),
        )


@router.message(BeatpackState.waiting_for_audio, has_audio_file)
async def beatpack_audio_handler(message: Message, state: FSMContext, bot: Bot):
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
        pending_audio_file_id=audio_file_id,
        pending_audio_file_name=audio_file_name,
    )
    await cleanup_messages(bot, state, message.chat.id)
    await state.set_state(BeatpackState.waiting_for_collab_answer)
    await answer_and_track(
        message,
        state,
        "Этот бит коллабный?",
        reply_markup=get_collab_keyboard(),
    )


@router.message(BeatpackState.waiting_for_audio, is_not_command)
async def wrong_beatpack_audio_handler(message: Message, state: FSMContext):
    await add_cleanup_message(state, message)
    await answer_and_track(
        message,
        state,
        "Сейчас нужно отправить mp3-бит.",
        reply_markup=get_start_keyboard(),
    )


@router.callback_query(BeatpackState.waiting_for_collab_answer, F.data == "beatpack:collab:yes")
async def beatpack_collab_yes_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    await add_cleanup_message(state, callback.message)

    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        await cleanup_messages(bot, state, callback.message.chat.id)
        await state.set_state(BeatpackState.waiting_for_author_links)
        await answer_and_track(
            callback.message,
            state,
            "Отправьте ссылки на авторов через пробел, запятую или с новой строки.",
            reply_markup=get_start_keyboard(),
        )


@router.callback_query(BeatpackState.waiting_for_collab_answer, F.data == "beatpack:collab:no")
async def beatpack_collab_no_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    await add_cleanup_message(state, callback.message)
    await state.update_data(pending_authors=[])

    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        await cleanup_messages(bot, state, callback.message.chat.id)
        await ask_for_file_name(callback.message, state)


@router.message(BeatpackState.waiting_for_author_links, F.text)
async def beatpack_author_links_handler(message: Message, state: FSMContext, bot: Bot):
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

    await state.update_data(pending_authors=authors)
    await cleanup_messages(bot, state, message.chat.id)
    await ask_for_file_name(message, state)


@router.message(BeatpackState.waiting_for_author_links, is_not_command)
async def wrong_author_links_handler(message: Message, state: FSMContext):
    await add_cleanup_message(state, message)
    await answer_and_track(
        message,
        state,
        "Сейчас нужно отправить ссылки на авторов.",
        reply_markup=get_start_keyboard(),
    )


@router.message(BeatpackState.waiting_for_file_name, F.text, is_not_command)
async def beatpack_file_name_handler(message: Message, state: FSMContext, bot: Bot):
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

    await state.update_data(pending_audio_file_name=file_name)
    tracks_count = await save_pending_track(state)
    await cleanup_messages(bot, state, message.chat.id)
    await state.set_state(BeatpackState.choosing_next_step)
    await answer_and_track(
        message,
        state,
        f"Бит добавлен. Всего битов: {tracks_count}.",
        reply_markup=get_next_step_keyboard(),
    )


@router.callback_query(BeatpackState.waiting_for_file_name, F.data == "beatpack:file_name:keep")
async def beatpack_keep_file_name_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    await add_cleanup_message(state, callback.message)

    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        tracks_count = await save_pending_track(state)
        await cleanup_messages(bot, state, callback.message.chat.id)
        await state.set_state(BeatpackState.choosing_next_step)
        await answer_and_track(
            callback.message,
            state,
            f"Бит добавлен. Всего битов: {tracks_count}.",
            reply_markup=get_next_step_keyboard(),
        )


@router.message(BeatpackState.waiting_for_file_name, is_not_command)
async def wrong_beatpack_file_name_handler(message: Message, state: FSMContext):
    await add_cleanup_message(state, message)
    await answer_and_track(
        message,
        state,
        "Сейчас нужно отправить новое название файла текстом.",
        reply_markup=get_start_keyboard(),
    )


@router.callback_query(BeatpackState.choosing_next_step, F.data == "beatpack:add")
async def beatpack_add_more_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    await add_cleanup_message(state, callback.message)

    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        await cleanup_messages(bot, state, callback.message.chat.id)
        await state.set_state(BeatpackState.waiting_for_audio)
        await answer_and_track(
            callback.message,
            state,
            "Отправьте следующий mp3-бит.",
            reply_markup=get_start_keyboard(),
        )


@router.callback_query(BeatpackState.choosing_next_step, F.data == "beatpack:done")
async def beatpack_done_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    await add_cleanup_message(state, callback.message)
    data = await state.get_data()

    if not data.get("tracks"):
        await state.set_state(BeatpackState.waiting_for_audio)

        if callback.message:
            await cleanup_messages(bot, state, callback.message.chat.id)
            await answer_and_track(
                callback.message,
                state,
                "Сначала нужно добавить хотя бы один mp3-бит.",
                reply_markup=get_start_keyboard(),
            )
        return

    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        await cleanup_messages(bot, state, callback.message.chat.id)
        await ask_for_cover(callback.message, state)


@router.message(BeatpackState.waiting_for_cover, F.photo)
@router.message(BeatpackState.waiting_for_cover, F.document)
async def beatpack_cover_handler(
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

    await build_and_send_beatpack(message, state, bot, db_session, cover_file_id, message.from_user)


@router.callback_query(BeatpackState.waiting_for_cover, F.data == "beatpack:cover:skip")
async def beatpack_skip_cover_handler(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    db_session: AsyncSession,
):
    await callback.answer()
    await add_cleanup_message(state, callback.message)

    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        await build_and_send_beatpack(
            callback.message,
            state,
            bot,
            db_session,
            None,
            callback.from_user,
        )


@router.message(BeatpackState.waiting_for_cover, is_not_command)
async def wrong_cover_handler(message: Message, state: FSMContext):
    await add_cleanup_message(state, message)
    await answer_and_track(
        message,
        state,
        "Сейчас нужно отправить обложку как фото/файл JPEG/PNG или нажать «Без обложки».",
        reply_markup=get_start_keyboard(),
    )
