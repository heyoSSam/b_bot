import re
from urllib.parse import urlparse

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from bot.services.subscription_service import get_channel_url, get_channel_username


class TooManyAuthorsError(Exception):
    pass


def split_author_tokens(text: str) -> list[str]:
    return [
        token.strip(" ,;\n\t")
        for token in re.split(r"[\s,]+", text.strip())
        if token.strip(" ,;\n\t")
    ]


def normalize_author_url(value: str) -> str | None:
    username = get_channel_username(value)

    if not username:
        return None

    return get_channel_url(username)


def get_telegram_username(url: str) -> str | None:
    parsed = urlparse(url)

    if parsed.netloc.lower() not in {"t.me", "telegram.me"}:
        return None

    username = parsed.path.strip("/").split("/", 1)[0]

    if not username or username in {"c", "joinchat", "+"} or username.startswith("+"):
        return None

    return username


def get_fallback_label(url: str) -> str:
    parsed = urlparse(url)

    if parsed.netloc.lower() in {"t.me", "telegram.me"}:
        username = get_telegram_username(url)

        if username:
            return username

    if parsed.netloc:
        return parsed.netloc.removeprefix("www.")

    return url


async def resolve_author(bot: Bot, value: str) -> dict[str, str] | None:
    url = normalize_author_url(value)

    if not url:
        return None

    label = get_fallback_label(url)
    username = get_telegram_username(url)

    if username:
        try:
            chat = await bot.get_chat(f"@{username}")
        except TelegramAPIError:
            return {"label": label, "url": url}

        if getattr(chat, "title", None):
            label = chat.title
        elif getattr(chat, "username", None):
            label = chat.username

    return {"label": label, "url": url}


async def resolve_authors(bot: Bot, text: str) -> list[dict[str, str]]:
    return await resolve_authors_with_limit(bot, text)


async def resolve_authors_with_limit(
    bot: Bot,
    text: str,
    max_authors: int | None = None,
) -> list[dict[str, str]]:
    authors = []
    seen_urls = set()

    for token in split_author_tokens(text):
        url = normalize_author_url(token)

        if not url or url in seen_urls:
            continue

        if max_authors is not None and len(seen_urls) >= max_authors:
            raise TooManyAuthorsError

        author = await resolve_author(bot, url)

        if not author:
            continue

        authors.append(author)
        seen_urls.add(url)

    return authors
