import re
from urllib.parse import urlparse

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError


def split_author_tokens(text: str) -> list[str]:
    return [
        token.strip(" ,;\n\t")
        for token in re.split(r"[\s,]+", text.strip())
        if token.strip(" ,;\n\t")
    ]


def normalize_author_url(value: str) -> str | None:
    token = value.strip()

    if token.startswith("@") and len(token) > 1:
        return f"https://t.me/{token[1:]}"

    if token.startswith("t.me/"):
        return f"https://{token}"

    if token.startswith(("http://", "https://", "tg://")):
        return token

    return None


def get_telegram_username(url: str) -> str | None:
    parsed = urlparse(url)

    if parsed.scheme == "tg":
        return None

    if parsed.netloc.lower() not in {"t.me", "telegram.me"}:
        return None

    username = parsed.path.strip("/").split("/", 1)[0]

    if not username or username in {"c", "joinchat", "+"} or username.startswith("+"):
        return None

    return username


def get_fallback_label(url: str) -> str:
    parsed = urlparse(url)

    if parsed.scheme == "tg":
        return "автор"

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
    authors = []
    seen_urls = set()

    for token in split_author_tokens(text):
        author = await resolve_author(bot, token)

        if not author or author["url"] in seen_urls:
            continue

        authors.append(author)
        seen_urls.add(author["url"])

    return authors
