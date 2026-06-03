import logging
import os
from urllib.parse import urlparse

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.constants import SUBSCRIPTION_REQUIRED_TEXT
from bot.keyboards.common import with_start_button


logger = logging.getLogger(__name__)


def get_required_channel_value() -> str | None:
    value = os.getenv("REQUIRED_CHANNEL_USERNAME")

    if not value:
        return None

    value = value.strip()

    if not value:
        return None

    return value


def get_channel_username(value: str) -> str | None:
    if value.startswith("@") and len(value) > 1:
        return value

    if value.startswith("t.me/"):
        value = f"https://{value}"

    if value.startswith(("http://", "https://")):
        parsed = urlparse(value)

        if parsed.netloc.lower() not in {"t.me", "telegram.me"}:
            return None

        username = parsed.path.strip("/").split("/", 1)[0]

        if not username or username.startswith("+") or username in {"c", "joinchat"}:
            return None

        return f"@{username}"

    return f"@{value}"


def get_channel_url(value: str) -> str:
    if value.startswith(("http://", "https://")):
        return value

    if value.startswith("t.me/"):
        return f"https://{value}"

    if value.startswith("@"):
        return f"https://t.me/{value[1:]}"

    return f"https://t.me/{value}"


def get_subscription_keyboard(command: str) -> InlineKeyboardMarkup:
    channel_value = get_required_channel_value()
    channel_url = get_channel_url(channel_value) if channel_value else "https://t.me/"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Подписаться", url=channel_url)],
            [InlineKeyboardButton(text="Проверить", callback_data=f"subscription:check:{command}")],
        ]
    )


async def is_user_subscribed(bot: Bot, user_id: int) -> bool:
    channel_value = get_required_channel_value()

    if not channel_value:
        return True

    channel_username = get_channel_username(channel_value)

    if not channel_username:
        logger.error("REQUIRED_CHANNEL_USERNAME must be a public Telegram channel link or @username")
        return False

    try:
        member = await bot.get_chat_member(chat_id=channel_username, user_id=user_id)
    except TelegramAPIError:
        logger.exception("Failed to check subscription for channel %s", channel_username)
        return False

    return member.status not in {"left", "kicked"}


async def require_subscription(message: Message, bot: Bot, command: str) -> bool:
    if not message.from_user:
        return False

    if await is_user_subscribed(bot, message.from_user.id):
        return True

    await message.answer(
        SUBSCRIPTION_REQUIRED_TEXT,
        reply_markup=with_start_button(get_subscription_keyboard(command)),
    )
    return False
