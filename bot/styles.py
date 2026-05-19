import html
import re
from urllib.parse import urlparse

from aiogram.types import Message, User as TelegramUser

from bot.constants import BOT_CREDIT_TEXT, DEFAULT_NAME_STYLE, NAME_STYLE_TOKEN_PATTERN
from bot.models import User


name_style_token_pattern = re.compile(NAME_STYLE_TOKEN_PATTERN)


def get_user_url(message: Message, telegram_user: TelegramUser | None = None) -> str | None:
    user = telegram_user or message.from_user

    if not user:
        return None

    if user.username:
        return f"https://t.me/{user.username}"

    return f"tg://user?id={user.id}"


def get_user_link_label(message: Message, telegram_user: TelegramUser | None = None) -> str:
    user = telegram_user or message.from_user

    if not user:
        return "ЛС"

    if user.username:
        return f"@{user.username}"

    return getattr(user, "full_name", None) or getattr(user, "first_name", None) or "ЛС"


def build_link(url: str, label: str) -> str:
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'


def get_channel_label(channel_url: str) -> str:
    parsed = urlparse(channel_url)
    path = parsed.path.strip("/")

    if not path or path.startswith("+") or path.startswith("joinchat"):
        return "канал"

    return path.split("/", 1)[0]


def render_author_links(authors: list[dict[str, str]]) -> str:
    return ", ".join(
        build_link(author["url"], author["label"])
        for author in authors
    )


def render_name_style(
    style: str,
    message: Message,
    authors: list[dict[str, str]] | None = None,
    user: User | None = None,
    telegram_user: TelegramUser | None = None,
) -> str:
    author_links = render_author_links(authors or [])
    channel_url = user.telegram_channel_url if user else None
    user_url = get_user_url(message, telegram_user)
    result = []
    position = 0

    for match in name_style_token_pattern.finditer(style):
        result.append(html.escape(style[position:match.start()]))
        token_name = match.group(1)
        token_value = match.group(2)

        if token_name == "me":
            label = (token_value or "").strip() or get_user_link_label(message, telegram_user)
            result.append(build_link(user_url, label) if user_url else html.escape(label))
        elif token_name == "channel":
            if channel_url:
                label = (token_value or "").strip() or get_channel_label(channel_url)
                result.append(build_link(channel_url, label))
        elif token_name == "co-author" and author_links:
            result.append(f"{html.escape(token_value or '')}{author_links}")

        position = match.end()

    result.append(html.escape(style[position:]))
    return "".join(result).strip()


def build_track_caption_for_style(
    style: str,
    message: Message,
    authors: list[dict[str, str]] | None = None,
    text: str | None = None,
    user: User | None = None,
    telegram_user: TelegramUser | None = None,
) -> str:
    footer = render_name_style(style, message, authors, user, telegram_user)
    footer = f"{footer}\n\n{html.escape(BOT_CREDIT_TEXT)}" if footer else html.escape(BOT_CREDIT_TEXT)

    if text and text.strip():
        return f"{html.escape(text.strip())}\n\n{footer}"

    return footer


def build_track_caption(
    message: Message,
    authors: list[dict[str, str]] | None = None,
    text: str | None = None,
    user: User | None = None,
    telegram_user: TelegramUser | None = None,
) -> str:
    style = user.name_style if user else DEFAULT_NAME_STYLE
    return build_track_caption_for_style(style, message, authors, text, user, telegram_user)
