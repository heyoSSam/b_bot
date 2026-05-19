import html
import re
from urllib.parse import urlparse, urlunparse

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bot.authors import resolve_author
from bot.cleanup import add_cleanup_message, answer_and_track, cleanup_messages
from bot.constants import (
    DEFAULT_NAME_STYLE,
    NAME_STYLE_MAX_LENGTH,
    NAME_STYLE_TOKEN_PATTERN,
    SET_CHANNEL_GUIDE_TEXT,
    SET_STYLE_CO_AUTHOR_TEXT_INPUT_PROMPT,
    SET_STYLE_CONSTRUCTOR_TEXT,
    SET_STYLE_ME_TEXT_INPUT_PROMPT,
    SET_STYLE_PREVIEW_TEXT,
    SET_STYLE_RAW_INPUT_PROMPT,
    SET_STYLE_RAW_INPUT_WITHOUT_CHANNEL_PROMPT,
    SET_STYLE_TEXT_INPUT_PROMPT,
    START_GUIDE_TEXT,
)
from bot.navigation import get_start_keyboard
from bot.styles import build_track_caption_for_style, get_channel_label
from bot.subscription import get_channel_url, get_required_channel_value
from bot.user_storage import get_user, set_user_channel, set_user_name_style


router = Router()


class SettingsState(StatesGroup):
    waiting_for_channel = State()
    editing_style = State()
    choosing_style_me = State()
    choosing_style_co_author = State()
    waiting_for_style = State()
    waiting_for_style_me_text = State()
    waiting_for_style_co_author_text = State()
    waiting_for_style_text = State()


def is_not_command(message: Message) -> bool:
    return not (message.text and message.text.startswith("/"))


def normalize_channel_url(value: str) -> str | None:
    channel = value.strip()

    if not channel or any(character.isspace() for character in channel):
        return None

    if channel.startswith("@") and len(channel) > 1:
        return f"https://t.me/{channel[1:]}"

    if channel.startswith("t.me/"):
        channel = f"https://{channel}"

    if not channel.startswith(("http://", "https://")):
        return f"https://t.me/{channel}"

    parsed = urlparse(channel)

    if parsed.netloc.lower() not in {"t.me", "telegram.me"}:
        return None

    if not parsed.path.strip("/"):
        return None

    return urlunparse(("https", "t.me", parsed.path.rstrip("/"), "", "", ""))


def clean_name_style(value: str, has_channel: bool = True) -> str | None:
    style = value.strip()

    if get_name_style_validation_error(style, has_channel):
        return None

    return style


def has_unknown_name_style_braces(style: str) -> bool:
    position = 0

    for match in re.finditer(NAME_STYLE_TOKEN_PATTERN, style):
        if "{" in style[position:match.start()] or "}" in style[position:match.start()]:
            return True

        position = match.end()

    return "{" in style[position:] or "}" in style[position:]


def has_channel_token(style: str) -> bool:
    return any(
        match.group(1) == "channel"
        for match in re.finditer(NAME_STYLE_TOKEN_PATTERN, style)
    )


def get_name_style_validation_error(value: str, has_channel: bool = True) -> str | None:
    style = value.strip()

    if not style:
        return f"Отправьте непустой шаблон до {NAME_STYLE_MAX_LENGTH} символов."

    if len(style) > NAME_STYLE_MAX_LENGTH:
        return f"Шаблон слишком длинный. Максимум: {NAME_STYLE_MAX_LENGTH} символов."

    if has_unknown_name_style_braces(style):
        return "Не понял переменную в фигурных скобках. Используйте кнопки конструктора или доступные переменные."

    if not has_channel and has_channel_token(style):
        return "Сначала сохраните канал через /set_channel, потом добавьте {channel} в шаблон."

    return None


def get_style_display(style: str) -> str:
    return html.escape(style) if style else "пусто"


def add_trailing_space(value: str) -> str:
    return value if value.endswith(" ") else f"{value} "


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
                InlineKeyboardButton(text="В старт", callback_data="navigation:start"),
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
                InlineKeyboardButton(text="В старт", callback_data="navigation:start"),
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
                InlineKeyboardButton(text="В старт", callback_data="navigation:start"),
            ],
        ]
    )


def build_style_constructor_text(style: str, notice: str | None = None) -> str:
    notice_text = f"\n\n{html.escape(notice)}" if notice else ""
    return SET_STYLE_CONSTRUCTOR_TEXT.format(style=get_style_display(style), notice=notice_text)


async def get_style_draft(state: FSMContext) -> str:
    data = await state.get_data()
    return data.get("style_draft") or ""


async def get_style_has_channel(state: FSMContext) -> bool:
    data = await state.get_data()
    return bool(data.get("style_has_channel"))


async def get_style_raw_input_prompt(state: FSMContext) -> str:
    if await get_style_has_channel(state):
        return SET_STYLE_RAW_INPUT_PROMPT

    return SET_STYLE_RAW_INPUT_WITHOUT_CHANNEL_PROMPT


async def update_style_draft(state: FSMContext, style: str) -> None:
    data = await state.get_data()
    history = list(data.get("style_history", []))
    history.append(data.get("style_draft") or "")
    await state.update_data(style_draft=style, style_history=history)


async def send_style_constructor(
    message: Message,
    state: FSMContext,
    style: str,
    notice: str | None = None,
) -> None:
    has_channel = await get_style_has_channel(state)
    await answer_and_track(
        message,
        state,
        build_style_constructor_text(style, notice),
        parse_mode="HTML",
        reply_markup=get_style_constructor_keyboard(has_channel),
    )


async def refresh_style_constructor(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    style: str,
    notice: str | None = None,
) -> None:
    await add_cleanup_message(state, callback.message)

    if not callback.message:
        return

    await cleanup_messages(bot, state, callback.message.chat.id)
    await state.set_state(SettingsState.editing_style)
    await send_style_constructor(callback.message, state, style, notice)


async def append_style_part(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    part: str,
    notice: str,
) -> None:
    draft_style = await get_style_draft(state)
    style = f"{draft_style}{part}"
    error = get_name_style_validation_error(style, await get_style_has_channel(state))

    if error:
        await callback.answer(error, show_alert=True)
        return

    await callback.answer()
    await update_style_draft(state, style)
    await refresh_style_constructor(callback, state, bot, style, notice)


async def get_style_preview_authors(bot: Bot) -> list[dict[str, str]]:
    channel_value = get_required_channel_value()

    if not channel_value:
        return []

    author = await resolve_author(bot, channel_value)

    if author:
        return [author]

    channel_url = get_channel_url(channel_value)
    author = await resolve_author(bot, channel_url)

    if author:
        return [author]

    return [{"label": get_channel_label(channel_url), "url": channel_url}]


async def save_channel(
    message: Message,
    state: FSMContext,
    bot: Bot,
    db_session: AsyncSession,
    value: str,
) -> None:
    await add_cleanup_message(state, message)

    if not message.from_user:
        return

    channel_url = normalize_channel_url(value)

    if not channel_url:
        await answer_and_track(
            message,
            state,
            "Не понял ссылку. Отправьте @channel или https://t.me/channel.",
            reply_markup=get_start_keyboard(),
        )
        return

    await set_user_channel(db_session, message.from_user, channel_url)
    await cleanup_messages(bot, state, message.chat.id)
    await state.clear()
    await message.answer(f"Канал сохранён: {channel_url}\n\n{START_GUIDE_TEXT}")


@router.message(Command("set_channel"))
async def start_set_channel(
    message: Message,
    state: FSMContext,
    bot: Bot,
):
    await cleanup_messages(bot, state, message.chat.id)
    await state.clear()
    await add_cleanup_message(state, message)
    await state.set_state(SettingsState.waiting_for_channel)
    await answer_and_track(
        message,
        state,
        SET_CHANNEL_GUIDE_TEXT,
        parse_mode="HTML",
        reply_markup=get_start_keyboard(),
    )


@router.message(SettingsState.waiting_for_channel, F.text, is_not_command)
async def set_channel_handler(
    message: Message,
    state: FSMContext,
    bot: Bot,
    db_session: AsyncSession,
):
    await save_channel(message, state, bot, db_session, message.text)


@router.message(Command("set_style"))
async def start_set_style(
    message: Message,
    state: FSMContext,
    bot: Bot,
    db_session: AsyncSession,
):
    await cleanup_messages(bot, state, message.chat.id)
    await state.clear()
    await add_cleanup_message(state, message)
    await state.set_state(SettingsState.editing_style)

    user = await get_user(db_session, message.from_user.id) if message.from_user else None
    has_channel = bool(user and user.telegram_channel_url)
    style = user.name_style if user else DEFAULT_NAME_STYLE
    await state.update_data(
        style_draft=style,
        style_has_channel=has_channel,
        style_history=[],
    )
    await send_style_constructor(message, state, style)


@router.callback_query(SettingsState.editing_style, F.data == "settings:style:add_me")
async def add_me_to_style(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    await add_cleanup_message(state, callback.message)

    if not callback.message:
        return

    await cleanup_messages(bot, state, callback.message.chat.id)
    await state.set_state(SettingsState.choosing_style_me)
    await answer_and_track(
        callback.message,
        state,
        "Выберите текст ссылки на личные сообщения.",
        parse_mode="HTML",
        reply_markup=get_style_me_keyboard(),
    )


@router.callback_query(SettingsState.choosing_style_me, F.data == "settings:style:me_username")
async def add_username_me_to_style(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await append_style_part(
        callback,
        state,
        bot,
        "{me} ",
        "Добавлена ссылка на личные сообщения.",
    )


@router.callback_query(SettingsState.choosing_style_me, F.data == "settings:style:me_custom")
async def start_custom_me_text(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    await add_cleanup_message(state, callback.message)

    if not callback.message:
        return

    await cleanup_messages(bot, state, callback.message.chat.id)
    await state.set_state(SettingsState.waiting_for_style_me_text)
    await answer_and_track(
        callback.message,
        state,
        SET_STYLE_ME_TEXT_INPUT_PROMPT,
        reply_markup=get_start_keyboard(),
    )


@router.callback_query(SettingsState.editing_style, F.data == "settings:style:add_channel")
async def add_channel_to_style(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not await get_style_has_channel(state):
        await callback.answer("Сначала сохраните канал через /set_channel.", show_alert=True)
        return

    await append_style_part(
        callback,
        state,
        bot,
        "{channel}",
        "Добавлена ссылка на сохранённый канал. Если канал ещё не сохранён, используйте /set_channel.",
    )


@router.callback_query(SettingsState.editing_style, F.data == "settings:style:add_co_author")
async def add_co_author_to_style(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    await add_cleanup_message(state, callback.message)

    if not callback.message:
        return

    await cleanup_messages(bot, state, callback.message.chat.id)
    await state.set_state(SettingsState.choosing_style_co_author)
    await answer_and_track(
        callback.message,
        state,
        "Выберите текст перед соавторами.",
        parse_mode="HTML",
        reply_markup=get_style_co_author_keyboard(),
    )


@router.callback_query(SettingsState.choosing_style_co_author, F.data == "settings:style:co_author_empty")
async def add_empty_co_author_to_style(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await append_style_part(
        callback,
        state,
        bot,
        "{co-author}",
        "Добавлен блок соавторов без текста перед ним.",
    )


@router.callback_query(SettingsState.choosing_style_co_author, F.data == "settings:style:co_author_custom")
async def start_custom_co_author_text(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    await add_cleanup_message(state, callback.message)

    if not callback.message:
        return

    await cleanup_messages(bot, state, callback.message.chat.id)
    await state.set_state(SettingsState.waiting_for_style_co_author_text)
    await answer_and_track(
        callback.message,
        state,
        SET_STYLE_CO_AUTHOR_TEXT_INPUT_PROMPT,
        reply_markup=get_start_keyboard(),
    )


@router.callback_query(
    SettingsState.choosing_style_me,
    F.data == "settings:style:back",
)
@router.callback_query(
    SettingsState.choosing_style_co_author,
    F.data == "settings:style:back",
)
async def back_to_style_constructor(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    style = await get_style_draft(state)
    await refresh_style_constructor(callback, state, bot, style)


@router.callback_query(SettingsState.editing_style, F.data == "settings:style:add_text")
async def start_add_style_text(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    await add_cleanup_message(state, callback.message)

    if not callback.message:
        return

    await cleanup_messages(bot, state, callback.message.chat.id)
    await state.set_state(SettingsState.waiting_for_style_text)
    await answer_and_track(
        callback.message,
        state,
        SET_STYLE_TEXT_INPUT_PROMPT,
        reply_markup=get_start_keyboard(),
    )


@router.callback_query(SettingsState.editing_style, F.data == "settings:style:manual")
async def start_manual_style_input(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    await add_cleanup_message(state, callback.message)

    if not callback.message:
        return

    await cleanup_messages(bot, state, callback.message.chat.id)
    await state.set_state(SettingsState.waiting_for_style)
    await answer_and_track(
        callback.message,
        state,
        await get_style_raw_input_prompt(state),
        parse_mode="HTML",
        reply_markup=get_start_keyboard(),
    )


@router.callback_query(SettingsState.editing_style, F.data == "settings:style:clear")
async def clear_style_draft(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    await update_style_draft(state, "")
    await refresh_style_constructor(callback, state, bot, "", "Шаблон очищен.")


@router.callback_query(SettingsState.editing_style, F.data == "settings:style:undo")
async def undo_style_draft(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    history = list(data.get("style_history", []))

    if not history:
        await callback.answer("Нет шага для отмены.", show_alert=True)
        return

    style = history.pop()
    await state.update_data(style_draft=style, style_history=history)
    await callback.answer()
    await refresh_style_constructor(callback, state, bot, style, "Последний шаг отменён.")


@router.callback_query(SettingsState.editing_style, F.data == "settings:style:preview")
async def preview_style_draft(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    db_session: AsyncSession,
):
    style = await get_style_draft(state)
    has_channel = await get_style_has_channel(state)
    error = get_name_style_validation_error(style, has_channel)

    if error:
        await callback.answer(error, show_alert=True)
        return

    await callback.answer()
    await add_cleanup_message(state, callback.message)

    if not callback.message:
        return

    user = await get_user(db_session, callback.from_user.id)
    authors = await get_style_preview_authors(bot)
    preview = build_track_caption_for_style(
        style,
        callback.message,
        authors,
        user=user,
        telegram_user=callback.from_user,
    )

    await cleanup_messages(bot, state, callback.message.chat.id)
    await state.set_state(SettingsState.editing_style)
    await answer_and_track(
        callback.message,
        state,
        SET_STYLE_PREVIEW_TEXT.format(
            preview=preview,
            style=get_style_display(style),
        ),
        parse_mode="HTML",
        link_preview_options=LinkPreviewOptions(is_disabled=True),
        reply_markup=get_style_constructor_keyboard(has_channel),
    )


@router.callback_query(SettingsState.editing_style, F.data == "settings:style:save")
async def save_style_draft(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    db_session: AsyncSession,
):
    style = await get_style_draft(state)
    error = get_name_style_validation_error(style, await get_style_has_channel(state))

    if error:
        await callback.answer(error, show_alert=True)
        return

    await callback.answer()
    await set_user_name_style(db_session, callback.from_user, style.strip())
    await add_cleanup_message(state, callback.message)

    if callback.message:
        await cleanup_messages(bot, state, callback.message.chat.id)

    await state.clear()

    if callback.message:
        await callback.message.answer(f"Шаблон подписи сохранён.\n\n{START_GUIDE_TEXT}")


@router.message(SettingsState.waiting_for_style, F.text, is_not_command)
async def set_style_handler(
    message: Message,
    state: FSMContext,
    bot: Bot,
):
    await add_cleanup_message(state, message)
    has_channel = await get_style_has_channel(state)
    style = clean_name_style(message.text, has_channel)

    if not style:
        await answer_and_track(
            message,
            state,
            get_name_style_validation_error(message.text, has_channel)
            or f"Отправьте непустой шаблон до {NAME_STYLE_MAX_LENGTH} символов.",
            reply_markup=get_start_keyboard(),
        )
        return

    await update_style_draft(state, style)
    await cleanup_messages(bot, state, message.chat.id)
    await state.set_state(SettingsState.editing_style)
    await send_style_constructor(
        message,
        state,
        style,
        "Шаблон обновлён. Проверьте предпросмотр и сохраните.",
    )


@router.message(SettingsState.waiting_for_style_text, F.text, is_not_command)
async def add_style_text_handler(message: Message, state: FSMContext, bot: Bot):
    await add_cleanup_message(state, message)
    text = message.text

    if not text or not text.strip():
        await answer_and_track(
            message,
            state,
            "Отправьте непустой текст для добавления в шаблон.",
            reply_markup=get_start_keyboard(),
        )
        return

    draft_style = await get_style_draft(state)
    style = f"{draft_style}{text}"
    error = get_name_style_validation_error(style, await get_style_has_channel(state))

    if error:
        await answer_and_track(
            message,
            state,
            error,
            reply_markup=get_start_keyboard(),
        )
        return

    await update_style_draft(state, style)
    await cleanup_messages(bot, state, message.chat.id)
    await state.set_state(SettingsState.editing_style)
    await send_style_constructor(message, state, style, "Текст добавлен.")


@router.message(SettingsState.waiting_for_style_me_text, F.text, is_not_command)
async def add_style_me_text_handler(message: Message, state: FSMContext, bot: Bot):
    await add_cleanup_message(state, message)
    text = message.text

    if not text or not text.strip():
        await answer_and_track(
            message,
            state,
            "Отправьте непустой текст для ссылки.",
            reply_markup=get_start_keyboard(),
        )
        return

    draft_style = await get_style_draft(state)
    style = f"{draft_style}{{me:{text}}} "
    error = get_name_style_validation_error(style, await get_style_has_channel(state))

    if error:
        await answer_and_track(
            message,
            state,
            error,
            reply_markup=get_start_keyboard(),
        )
        return

    await update_style_draft(state, style)
    await cleanup_messages(bot, state, message.chat.id)
    await state.set_state(SettingsState.editing_style)
    await send_style_constructor(message, state, style, "Добавлена ссылка на личные сообщения.")


@router.message(SettingsState.waiting_for_style_co_author_text, F.text, is_not_command)
async def add_style_co_author_text_handler(message: Message, state: FSMContext, bot: Bot):
    await add_cleanup_message(state, message)
    text = message.text

    if not text or not text.strip():
        await answer_and_track(
            message,
            state,
            "Отправьте непустой текст перед соавторами.",
            reply_markup=get_start_keyboard(),
        )
        return

    draft_style = await get_style_draft(state)
    style = f"{draft_style}{{co-author:{add_trailing_space(text.strip())}}}"
    error = get_name_style_validation_error(style, await get_style_has_channel(state))

    if error:
        await answer_and_track(
            message,
            state,
            error,
            reply_markup=get_start_keyboard(),
        )
        return

    await update_style_draft(state, style)
    await cleanup_messages(bot, state, message.chat.id)
    await state.set_state(SettingsState.editing_style)
    await send_style_constructor(message, state, style, "Добавлен блок соавторов.")


@router.message(SettingsState.waiting_for_style, is_not_command)
async def wrong_manual_style_input(message: Message, state: FSMContext):
    await add_cleanup_message(state, message)
    await answer_and_track(
        message,
        state,
        "Отправьте шаблон текстом.",
        reply_markup=get_start_keyboard(),
    )


@router.message(SettingsState.waiting_for_style_text, is_not_command)
async def wrong_style_text_input(message: Message, state: FSMContext):
    await add_cleanup_message(state, message)
    await answer_and_track(
        message,
        state,
        "Отправьте текст, который нужно добавить в шаблон.",
        reply_markup=get_start_keyboard(),
    )


@router.message(SettingsState.waiting_for_style_me_text, is_not_command)
async def wrong_style_me_text_input(message: Message, state: FSMContext):
    await add_cleanup_message(state, message)
    await answer_and_track(
        message,
        state,
        "Отправьте текст для ссылки на личные сообщения.",
        reply_markup=get_start_keyboard(),
    )


@router.message(SettingsState.waiting_for_style_co_author_text, is_not_command)
async def wrong_style_co_author_text_input(message: Message, state: FSMContext):
    await add_cleanup_message(state, message)
    await answer_and_track(
        message,
        state,
        "Отправьте текст перед соавторами.",
        reply_markup=get_start_keyboard(),
    )


@router.message(SettingsState.choosing_style_me, is_not_command)
async def wrong_style_me_choice(message: Message, state: FSMContext):
    await add_cleanup_message(state, message)
    await answer_and_track(
        message,
        state,
        "Выберите вариант кнопкой.",
        reply_markup=get_start_keyboard(),
    )


@router.message(SettingsState.choosing_style_co_author, is_not_command)
async def wrong_style_co_author_choice(message: Message, state: FSMContext):
    await add_cleanup_message(state, message)
    await answer_and_track(
        message,
        state,
        "Выберите вариант кнопкой.",
        reply_markup=get_start_keyboard(),
    )


@router.message(SettingsState.editing_style, is_not_command)
async def wrong_style_constructor_input(message: Message, state: FSMContext):
    await add_cleanup_message(state, message)
    await answer_and_track(
        message,
        state,
        "Используйте кнопки конструктора или выберите «Ввести шаблон вручную».",
        reply_markup=get_start_keyboard(),
    )
