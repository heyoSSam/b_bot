import asyncio
import logging
import os
import tempfile
from dataclasses import dataclass, field

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InputMediaAudio,
    Message,
    User as TelegramUser,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.user_storage import get_user, touch_user
from bot.handlers.settings import start_registration_if_needed
from bot.keyboards.beatpack import (
    get_beatpack_menu_keyboard,
    get_beatpack_track_action_keyboard,
    get_beatpack_track_position_keyboard,
    get_collab_keyboard,
    get_cover_keyboard,
    get_recent_authors_keyboard,
    with_beatpack_back_button,
)
from bot.keyboards.common import with_start_button
from bot.services.audio_service import (
    add_cover_bytes_to_mp3,
    create_audio_thumbnail,
    prepare_cover_bytes,
)
from bot.services.author_service import TooManyAuthorsError, resolve_authors_with_limit
from bot.services.caption_service import build_track_caption
from bot.services.cleanup_service import add_cleanup_message, answer_and_track, cleanup_messages
from bot.services.flow_service import (
    ask_for_author_links as ask_for_author_links_prompt,
    ask_for_cover as ask_for_cover_prompt,
    ask_for_file_name as ask_for_file_name_prompt,
    confirm_subscription,
    get_cover_file_id,
    get_mp3_file,
    handle_build_exception,
    has_audio_file,
    is_not_command,
    start_audio_flow,
)
from bot.states.beatpack import BeatpackState
from bot.constants import (
    AUTHOR_LIMIT_EXCEEDED_TEXT,
    BEATPACK_BUILD_MAX_CONCURRENCY,
    BEATPACK_MEDIA_GROUP_COLLECT_SECONDS,
    MAX_TRACK_AUTHORS,
)
from bot.utils.file_names import get_safe_audio_name


logger = logging.getLogger(__name__)
router = Router()


@dataclass
class BeatpackMediaGroupBatch:
    tracks: list[dict] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)
    invalid_count: int = 0
    state: FSMContext | None = None
    bot: Bot | None = None
    telegram_user: TelegramUser | None = None
    task: asyncio.Task | None = None


beatpack_media_group_batches: dict[tuple[int, int, str], BeatpackMediaGroupBatch] = {}


def get_recent_authors(data: dict) -> list[dict[str, str]]:
    authors = data.get("recent_authors", [])

    if not isinstance(authors, list):
        return []

    return [
        {"label": author["label"], "url": author["url"]}
        for author in authors
        if isinstance(author, dict) and author.get("label") and author.get("url")
    ]


async def append_tracks(state: FSMContext, new_tracks: list[dict]) -> int:
    data = await state.get_data()
    tracks = list(data.get("tracks", []))
    tracks.extend(new_tracks)
    await state.update_data(tracks=tracks)
    return len(tracks)


def get_track_from_mp3_file(mp3_file: tuple[str, str]) -> dict:
    audio_file_id, audio_file_name = mp3_file
    return {
        "file_id": audio_file_id,
        "file_name": audio_file_name,
        "authors": [],
    }


def get_indexed_track(data: dict) -> tuple[int | None, dict | None]:
    tracks = data.get("tracks", [])
    track_index = data.get("editing_track_index")

    if not isinstance(track_index, int) or track_index < 0 or track_index >= len(tracks):
        return None, None

    return track_index, tracks[track_index]


async def update_editing_track(state: FSMContext, **values) -> int | None:
    data = await state.get_data()
    track_index, track = get_indexed_track(data)

    if track_index is None or track is None:
        return None

    tracks = list(data.get("tracks", []))
    updated_track = dict(track)
    updated_track.update(values)
    tracks[track_index] = updated_track
    await state.update_data(tracks=tracks)
    return track_index


async def update_recent_authors(state: FSMContext, authors: list[dict[str, str]]) -> None:
    data = await state.get_data()
    recent_authors = get_recent_authors(data)
    authors_by_url = {author["url"]: author for author in recent_authors}

    for author in authors:
        url = author.get("url")
        label = author.get("label")

        if not url or not label:
            continue

        authors_by_url[url] = {"label": label, "url": url}

    await state.update_data(recent_authors=list(authors_by_url.values()))


async def move_editing_track(state: FSMContext, target_index: int) -> tuple[int | None, str | None]:
    data = await state.get_data()
    track_index, track = get_indexed_track(data)
    tracks = list(data.get("tracks", []))

    if track_index is None or track is None:
        return None, "Бит не найден."

    if target_index < 0 or target_index >= len(tracks):
        return track_index, "Не удалось изменить порядок."

    if target_index == track_index:
        return track_index, "Бит уже на этой позиции."

    tracks.pop(track_index)
    tracks.insert(target_index, track)
    track_index = target_index

    await state.update_data(tracks=tracks, editing_track_index=track_index)
    return track_index, None


async def delete_editing_track(state: FSMContext) -> bool:
    data = await state.get_data()
    track_index, _ = get_indexed_track(data)
    tracks = list(data.get("tracks", []))

    if track_index is None:
        return False

    tracks.pop(track_index)
    await state.update_data(tracks=tracks, editing_track_index=None)
    return True


def split_media(media: list[InputMediaAudio]) -> list[list[InputMediaAudio]]:
    return [media[index : index + 10] for index in range(0, len(media), 10)]


async def answer_media_audio(message: Message, media_audio: InputMediaAudio) -> Message:
    audio_kwargs = {
        "audio": media_audio.media,
        "caption": media_audio.caption,
        "parse_mode": media_audio.parse_mode,
    }
    title = getattr(media_audio, "title", None)

    if title:
        audio_kwargs["title"] = title

    if media_audio.thumbnail:
        audio_kwargs["thumbnail"] = media_audio.thumbnail

    return await message.answer_audio(**audio_kwargs)


async def ask_for_file_name(message: Message, state: FSMContext):
    data = await state.get_data()
    track_index, track = get_indexed_track(data)

    if track_index is None or track is None:
        await answer_and_track(
            message,
            state,
            "Бит не найден. Вернитесь к битпаку и выберите бит заново.",
            reply_markup=with_beatpack_back_button(),
        )
        return

    await ask_for_file_name_prompt(
        message,
        state,
        BeatpackState.waiting_for_file_name,
        track.get("file_name"),
        f"beat_{track_index + 1}.mp3",
        with_beatpack_back_button,
        "beatpack:file_name:keep",
    )


async def ask_for_cover(message: Message, state: FSMContext):
    await ask_for_cover_prompt(
        message,
        state,
        BeatpackState.waiting_for_cover,
        "Теперь отправьте обложку для битпака или нажмите «Без обложки».",
        get_cover_keyboard(),
    )


async def ask_for_author_links(message: Message, state: FSMContext, notice: str | None = None):
    data = await state.get_data()
    recent_authors = get_recent_authors(data)
    await ask_for_author_links_prompt(
        message,
        state,
        BeatpackState.waiting_for_author_links,
        with_beatpack_back_button(get_recent_authors_keyboard(recent_authors)),
        notice=notice,
        has_recent_authors=bool(recent_authors),
    )


async def send_beatpack_preview(
    message: Message,
    state: FSMContext,
    bot: Bot,
    db_session: AsyncSession,
    tracks: list[dict],
    telegram_user: TelegramUser | None,
) -> None:
    user = await get_user(db_session, telegram_user.id) if telegram_user else None
    media = []

    for index, track in enumerate(tracks, start=1):
        safe_name = get_safe_audio_name(track.get("file_name"), f"beat_{index}.mp3")
        media.append(
            InputMediaAudio(
                media=track["file_id"],
                caption=build_track_caption(
                    message,
                    track.get("authors", []),
                    user=user,
                    telegram_user=telegram_user,
                    include_bot_credit=index == len(tracks),
                ),
                parse_mode="HTML",
                title=safe_name,
            )
        )

    if len(media) == 1:
        sent_message = await answer_media_audio(message, media[0])
        await add_cleanup_message(state, sent_message)
        return

    for media_group in split_media(media):
        if len(media_group) == 1:
            sent_message = await answer_media_audio(message, media_group[0])
            await add_cleanup_message(state, sent_message)
            continue

        sent_messages = await bot.send_media_group(chat_id=message.chat.id, media=media_group)

        for sent_message in sent_messages:
            await add_cleanup_message(state, sent_message)


async def show_beatpack_menu(
    message: Message,
    state: FSMContext,
    bot: Bot,
    db_session: AsyncSession,
    telegram_user: TelegramUser | None,
    notice: str | None = None,
) -> None:
    data = await state.get_data()
    tracks = data.get("tracks", [])
    await cleanup_messages(bot, state, message.chat.id)

    if not tracks:
        await state.set_state(BeatpackState.waiting_for_audio)
        await answer_and_track(
            message,
            state,
            "Битпак пустой. Отправьте mp3-биты.",
            reply_markup=with_start_button(),
        )
        return

    await state.update_data(editing_track_index=None)
    await state.set_state(BeatpackState.choosing_next_step)
    await send_beatpack_preview(message, state, bot, db_session, tracks, telegram_user)

    text = f"Битпак сейчас: {len(tracks)} битов."

    if notice:
        text = f"{notice}\n\n{text}"

    await answer_and_track(
        message,
        state,
        f"{text}\nВыберите бит для редактирования или нажмите «Готово».",
        reply_markup=get_beatpack_menu_keyboard(tracks),
    )


async def show_beatpack_track_action_menu(
    message: Message,
    state: FSMContext,
    bot: Bot,
    notice: str | None = None,
) -> None:
    data = await state.get_data()
    track_index, track = get_indexed_track(data)
    tracks = data.get("tracks", [])

    if track_index is None or track is None:
        await answer_and_track(
            message,
            state,
            "Бит не найден. Вернитесь к битпаку и выберите бит заново.",
            reply_markup=with_beatpack_back_button(),
        )
        return

    safe_name = get_safe_audio_name(track.get("file_name"), f"beat_{track_index + 1}.mp3")
    text = f"Редактируем «{safe_name}». Позиция: {track_index + 1} из {len(tracks)}."

    if notice:
        text = f"{notice}\n\n{text}"

    await cleanup_messages(bot, state, message.chat.id)
    await state.set_state(BeatpackState.choosing_next_step)
    await answer_and_track(
        message,
        state,
        text,
        reply_markup=get_beatpack_track_action_keyboard(),
    )


async def flush_beatpack_media_group(key: tuple[int, int, str]) -> None:
    await asyncio.sleep(BEATPACK_MEDIA_GROUP_COLLECT_SECONDS)
    batch = beatpack_media_group_batches.pop(key, None)

    if not batch or not batch.state or not batch.bot or not batch.messages:
        return

    message = batch.messages[-1]
    current_state = await batch.state.get_state()

    if current_state not in (
        BeatpackState.waiting_for_audio.state,
        BeatpackState.choosing_next_step.state,
    ):
        return

    try:
        if not batch.tracks:
            await cleanup_messages(batch.bot, batch.state, message.chat.id)
            await batch.state.set_state(BeatpackState.waiting_for_audio)
            await answer_and_track(
                message,
                batch.state,
                "Пока поддерживаются только mp3-файлы.",
                reply_markup=with_start_button(),
            )
            return

        await append_tracks(batch.state, batch.tracks)
        notice = None

        if batch.invalid_count:
            notice = f"Добавлено mp3: {len(batch.tracks)}. Пропущено не mp3: {batch.invalid_count}."

        from bot.db.session import async_session as session_factory

        async with session_factory() as db_session:
            await show_beatpack_menu(
                message,
                batch.state,
                batch.bot,
                db_session,
                batch.telegram_user,
                notice,
            )
    except Exception:
        logger.exception("Failed to process beatpack media group")
        await cleanup_messages(batch.bot, batch.state, message.chat.id)
        await batch.state.set_state(BeatpackState.waiting_for_audio)
        await answer_and_track(
            message,
            batch.state,
            "Не удалось обработать биты. Отправьте mp3-файлы ещё раз.",
            reply_markup=with_start_button(),
        )


def add_to_beatpack_media_group(
    message: Message,
    state: FSMContext,
    bot: Bot,
    mp3_file: tuple[str, str] | None,
) -> bool:
    if not message.media_group_id:
        return False

    user_id = message.from_user.id if message.from_user else 0
    key = (message.chat.id, user_id, message.media_group_id)
    batch = beatpack_media_group_batches.get(key)

    if not batch:
        batch = BeatpackMediaGroupBatch()
        beatpack_media_group_batches[key] = batch

    batch.messages.append(message)
    batch.state = state
    batch.bot = bot
    batch.telegram_user = message.from_user

    if mp3_file:
        batch.tracks.append(get_track_from_mp3_file(mp3_file))
    else:
        batch.invalid_count += 1

    if not batch.task or batch.task.done():
        batch.task = asyncio.create_task(flush_beatpack_media_group(key))

    return True


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
            reply_markup=with_start_button(),
        )
        return

    await answer_and_track(message, state, f"Обрабатываю битпак. Битов: {len(tracks)}.")

    try:
        user = await get_user(db_session, telegram_user.id) if telegram_user else None

        with tempfile.TemporaryDirectory() as temp_dir:
            media = []
            cover_path = None
            cover_data = None
            thumbnail_path = None

            if cover_file_id:
                cover_path = os.path.join(temp_dir, "cover.jpg")
                thumbnail_path = os.path.join(temp_dir, "thumbnail.jpg")
                await bot.download(cover_file_id, destination=cover_path)
                create_audio_thumbnail(cover_path, thumbnail_path)
                cover_data = await asyncio.to_thread(prepare_cover_bytes, cover_path)

            semaphore = asyncio.Semaphore(BEATPACK_BUILD_MAX_CONCURRENCY)

            async def build_track_media(index: int, track: dict) -> InputMediaAudio:
                async with semaphore:
                    safe_name = get_safe_audio_name(track["file_name"], f"beat_{index}.mp3")
                    audio_path = os.path.join(temp_dir, f"{index}_{safe_name}")

                    await bot.download(track["file_id"], destination=audio_path)

                    if cover_data:
                        await asyncio.to_thread(add_cover_bytes_to_mp3, audio_path, cover_data)

                    media_kwargs = {
                        "media": FSInputFile(audio_path, filename=safe_name),
                        "caption": build_track_caption(
                            message,
                            track.get("authors", []),
                            user=user,
                            telegram_user=telegram_user,
                            include_bot_credit=index == len(tracks),
                        ),
                        "parse_mode": "HTML",
                    }

                    if thumbnail_path:
                        media_kwargs["thumbnail"] = FSInputFile(
                            thumbnail_path,
                            filename=f"thumbnail_{index}.jpg",
                        )

                    return InputMediaAudio(**media_kwargs)

            media = await asyncio.gather(
                *(build_track_media(index, track) for index, track in enumerate(tracks, start=1))
            )

            await cleanup_messages(bot, state, message.chat.id)

            for media_group in split_media(media):
                if len(media_group) == 1:
                    await answer_media_audio(message, media_group[0])
                    continue

                await bot.send_media_group(chat_id=message.chat.id, media=media_group)
            if telegram_user:
                await touch_user(db_session, telegram_user)
    except Exception as error:
        await handle_build_exception(
            message,
            state,
            bot,
            error,
            logger,
            "Failed to build beatpack",
            "Не удалось собрать битпак. Попробуйте снова через /beatpack.",
        )
        return

    await state.clear()


async def start_beatpack_flow(message: Message, state: FSMContext, bot: Bot) -> None:
    await start_audio_flow(
        message,
        state,
        bot,
        "beatpack",
        BeatpackState.waiting_for_audio,
        "Отправьте mp3-биты для битпака. Можно отправить несколько файлов сразу.",
        reset_data={"tracks": [], "recent_authors": []},
    )


@router.message(Command("beatpack"))
async def start_beatpack(
    message: Message,
    state: FSMContext,
    bot: Bot,
    db_session: AsyncSession,
):
    if await start_registration_if_needed(message, state, bot, db_session):
        return

    await start_beatpack_flow(message, state, bot)


@router.callback_query(F.data == "start:beatpack")
async def start_beatpack_from_menu(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()

    if callback.message:
        await start_beatpack_flow(callback.message, state, bot)


@router.callback_query(F.data == "subscription:check:beatpack")
async def check_beatpack_subscription(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await confirm_subscription(
        callback,
        state,
        bot,
        BeatpackState.waiting_for_audio,
        "Подписка подтверждена. Отправьте mp3-биты для битпака.",
        reset_data={"tracks": [], "recent_authors": []},
    )


@router.message(BeatpackState.waiting_for_audio, has_audio_file)
@router.message(BeatpackState.choosing_next_step, has_audio_file)
async def beatpack_audio_handler(
    message: Message,
    state: FSMContext,
    bot: Bot,
    db_session: AsyncSession,
):
    await add_cleanup_message(state, message)
    mp3_file = get_mp3_file(message)

    if add_to_beatpack_media_group(message, state, bot, mp3_file):
        return

    if not mp3_file:
        await answer_and_track(
            message,
            state,
            "Пока поддерживаются только mp3-файлы.",
            reply_markup=with_start_button(),
        )
        return

    await append_tracks(state, [get_track_from_mp3_file(mp3_file)])
    await show_beatpack_menu(
        message,
        state,
        bot,
        db_session,
        message.from_user,
    )


@router.message(BeatpackState.waiting_for_audio, is_not_command)
async def wrong_beatpack_audio_handler(message: Message, state: FSMContext):
    await add_cleanup_message(state, message)
    await answer_and_track(
        message,
        state,
        "Сейчас нужно отправить mp3-биты.",
        reply_markup=with_start_button(),
    )


@router.callback_query(BeatpackState.waiting_for_collab_answer, F.data == "beatpack:collab:yes")
async def beatpack_collab_yes_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    await add_cleanup_message(state, callback.message)

    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        await cleanup_messages(bot, state, callback.message.chat.id)
        await ask_for_author_links(callback.message, state)


@router.callback_query(BeatpackState.waiting_for_collab_answer, F.data == "beatpack:collab:no")
async def beatpack_collab_no_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    await add_cleanup_message(state, callback.message)
    await update_editing_track(state, authors=[])

    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        await show_beatpack_track_action_menu(callback.message, state, bot, "Соавторы убраны.")


@router.message(BeatpackState.waiting_for_author_links, F.text)
async def beatpack_author_links_handler(message: Message, state: FSMContext, bot: Bot):
    await add_cleanup_message(state, message)

    try:
        authors = await resolve_authors_with_limit(bot, message.text, MAX_TRACK_AUTHORS)
    except TooManyAuthorsError:
        await ask_for_author_links(
            message,
            state,
            AUTHOR_LIMIT_EXCEEDED_TEXT.format(max_authors=MAX_TRACK_AUTHORS),
        )
        return

    if not authors:
        await ask_for_author_links(
            message,
            state,
            "Отправьте хотя бы одну ссылку: https://..., t.me/... или @username.",
        )
        return

    await update_editing_track(state, authors=authors)
    await update_recent_authors(state, authors)
    await show_beatpack_track_action_menu(message, state, bot, "Соавторы обновлены.")


@router.message(BeatpackState.waiting_for_author_links, is_not_command)
async def wrong_author_links_handler(message: Message, state: FSMContext):
    await add_cleanup_message(state, message)
    await ask_for_author_links(message, state, "Сейчас нужно отправить ссылки на авторов.")


@router.message(BeatpackState.waiting_for_file_name, F.text, is_not_command)
async def beatpack_file_name_handler(
    message: Message,
    state: FSMContext,
    bot: Bot,
    db_session: AsyncSession,
):
    await add_cleanup_message(state, message)
    file_name = message.text.strip()

    if not file_name:
        await answer_and_track(
            message,
            state,
            "Отправьте новое название файла текстом.",
            reply_markup=with_beatpack_back_button(),
        )
        return

    updated_track_index = await update_editing_track(state, file_name=file_name)

    if updated_track_index is None:
        await answer_and_track(
            message,
            state,
            "Бит не найден. Вернитесь к битпаку и выберите бит заново.",
            reply_markup=with_beatpack_back_button(),
        )
        return

    await state.update_data(editing_track_index=None)
    await cleanup_messages(bot, state, message.chat.id)
    await show_beatpack_menu(
        message,
        state,
        bot,
        db_session,
        message.from_user,
        "Бит обновлён.",
    )


@router.callback_query(BeatpackState.waiting_for_file_name, F.data == "beatpack:file_name:keep")
async def beatpack_keep_file_name_handler(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    db_session: AsyncSession,
):
    await callback.answer()
    await add_cleanup_message(state, callback.message)

    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        await state.update_data(editing_track_index=None)
        await cleanup_messages(bot, state, callback.message.chat.id)
        await show_beatpack_menu(
            callback.message,
            state,
            bot,
            db_session,
            callback.from_user,
            "Бит обновлён.",
        )


@router.message(BeatpackState.waiting_for_file_name, is_not_command)
async def wrong_beatpack_file_name_handler(message: Message, state: FSMContext):
    await add_cleanup_message(state, message)
    await answer_and_track(
        message,
        state,
        "Сейчас нужно отправить новое название файла текстом.",
        reply_markup=with_beatpack_back_button(),
    )


@router.callback_query(BeatpackState.choosing_next_step, F.data.startswith("beatpack:edit:"))
async def beatpack_edit_track_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await add_cleanup_message(state, callback.message)

    if not callback.message:
        await callback.answer()
        return

    try:
        track_index = int((callback.data or "").rsplit(":", 1)[1])
    except ValueError:
        await callback.answer("Бит не найден.", show_alert=True)
        return

    data = await state.get_data()
    tracks = data.get("tracks", [])

    if track_index < 0 or track_index >= len(tracks):
        await callback.answer("Бит не найден.", show_alert=True)
        return

    safe_name = get_safe_audio_name(tracks[track_index].get("file_name"), f"beat_{track_index + 1}.mp3")
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await state.update_data(editing_track_index=track_index)
    await show_beatpack_track_action_menu(callback.message, state, bot, f"Выбран бит «{safe_name}».")


@router.callback_query(BeatpackState.choosing_next_step, F.data == "beatpack:track:file_name")
async def beatpack_track_file_name_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    await add_cleanup_message(state, callback.message)

    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        await cleanup_messages(bot, state, callback.message.chat.id)
        await ask_for_file_name(callback.message, state)


@router.callback_query(BeatpackState.choosing_next_step, F.data == "beatpack:track:authors")
async def beatpack_track_authors_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    await add_cleanup_message(state, callback.message)

    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        await cleanup_messages(bot, state, callback.message.chat.id)
        await ask_for_author_links(callback.message, state)


@router.callback_query(BeatpackState.choosing_next_step, F.data == "beatpack:track:move")
async def beatpack_track_move_menu_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await add_cleanup_message(state, callback.message)
    data = await state.get_data()
    tracks = data.get("tracks", [])
    track_index, track = get_indexed_track(data)

    if not callback.message:
        await callback.answer()
        return

    if track_index is None or track is None:
        await callback.answer("Бит не найден.", show_alert=True)
        return

    safe_name = get_safe_audio_name(track.get("file_name"), f"beat_{track_index + 1}.mp3")
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await cleanup_messages(bot, state, callback.message.chat.id)
    await answer_and_track(
        callback.message,
        state,
        f"Выберите новую позицию для «{safe_name}». Сейчас: {track_index + 1} из {len(tracks)}.",
        reply_markup=get_beatpack_track_position_keyboard(len(tracks)),
    )


@router.callback_query(BeatpackState.choosing_next_step, F.data == "beatpack:track:actions")
async def beatpack_track_actions_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    await add_cleanup_message(state, callback.message)

    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        await show_beatpack_track_action_menu(callback.message, state, bot)


@router.callback_query(BeatpackState.choosing_next_step, F.data.startswith("beatpack:track:position:"))
async def beatpack_track_move_handler(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    db_session: AsyncSession,
):
    await add_cleanup_message(state, callback.message)

    if not callback.message:
        await callback.answer()
        return

    try:
        target_index = int((callback.data or "").rsplit(":", 1)[1])
    except ValueError:
        await callback.answer("Не удалось изменить порядок.", show_alert=True)
        return

    _, error = await move_editing_track(state, target_index)

    if error:
        await callback.answer(error, show_alert=True)
        return

    await callback.answer()

    await callback.message.edit_reply_markup(reply_markup=None)
    await show_beatpack_menu(
        callback.message,
        state,
        bot,
        db_session,
        callback.from_user,
        "Порядок обновлён.",
    )


@router.callback_query(BeatpackState.choosing_next_step, F.data == "beatpack:track:delete")
async def beatpack_track_delete_handler(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    db_session: AsyncSession,
):
    await add_cleanup_message(state, callback.message)
    deleted = await delete_editing_track(state)

    if not deleted:
        await callback.answer("Бит не найден.", show_alert=True)
        return

    await callback.answer()

    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        await show_beatpack_menu(
            callback.message,
            state,
            bot,
            db_session,
            callback.from_user,
            "Бит удалён.",
        )


@router.callback_query(BeatpackState.choosing_next_step, F.data == "beatpack:menu")
@router.callback_query(BeatpackState.waiting_for_collab_answer, F.data == "beatpack:menu")
@router.callback_query(BeatpackState.waiting_for_author_links, F.data == "beatpack:menu")
@router.callback_query(BeatpackState.waiting_for_file_name, F.data == "beatpack:menu")
async def beatpack_back_to_menu_handler(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    db_session: AsyncSession,
):
    await callback.answer()
    await add_cleanup_message(state, callback.message)

    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        await show_beatpack_menu(
            callback.message,
            state,
            bot,
            db_session,
            callback.from_user,
        )


@router.callback_query(BeatpackState.choosing_next_step, F.data == "beatpack:add")
async def beatpack_add_more_handler(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    await add_cleanup_message(state, callback.message)

    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        await cleanup_messages(bot, state, callback.message.chat.id)
        await state.update_data(editing_track_index=None)
        await state.set_state(BeatpackState.waiting_for_audio)
        await answer_and_track(
            callback.message,
            state,
            "Отправьте mp3-биты для битпака.",
            reply_markup=with_start_button(),
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
                reply_markup=with_start_button(),
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
            reply_markup=with_start_button(),
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
        reply_markup=with_start_button(),
    )
