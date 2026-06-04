import logging
import os
import re
from urllib.parse import urlparse

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.constants import (
    SUBSCRIPTION_CHECK_FAILED_TEXT,
    SUBSCRIPTION_REQUIRED_TEXT,
    TELEGRAM_PUBLIC_NAME_PATTERN,
)
from bot.keyboards.common import with_start_button


logger = logging.getLogger(__name__)


class SubscriptionCheckError(Exception):
    pass


def get_required_channel_value() -> str | None:
    value = os.getenv("REQUIRED_CHANNEL_USERNAME")

    if not value:
        return None

    value = value.strip()

    if not value:
        return None

    return value


def normalize_public_channel_username(value: str) -> str | None:
    channel = value.strip()

    if not channel or any(character.isspace() for character in channel):
        return None

    if channel.startswith("@"):
        username = channel[1:]
    else:
        if channel.startswith("t.me/"):
            channel = f"https://{channel}"

        if channel.startswith(("http://", "https://")):
            parsed = urlparse(channel)

            if parsed.netloc.lower() not in {"t.me", "telegram.me"}:
                return None

            if parsed.query or parsed.fragment:
                return None

            path_parts = [part for part in parsed.path.split("/") if part]

            if len(path_parts) != 1:
                return None

            username = path_parts[0]
        else:
            username = channel

    if username.lower() in {"c", "joinchat"}:
        return None

    if not re.fullmatch(TELEGRAM_PUBLIC_NAME_PATTERN, username):
        return None

    return f"@{username}"


def get_channel_username(value: str) -> str | None:
    return normalize_public_channel_username(value)


def get_channel_url(value: str) -> str:
    channel_username = get_channel_username(value)

    if not channel_username:
        raise ValueError("Channel value must be a public Telegram username or URL")

    return f"https://t.me/{channel_username[1:]}"


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
        raise SubscriptionCheckError

    try:
        member = await bot.get_chat_member(chat_id=channel_username, user_id=user_id)
    except TelegramAPIError:
        logger.exception("Failed to check subscription for channel %s", channel_username)
        raise SubscriptionCheckError from None

    return member.status not in {"left", "kicked"}


async def require_subscription(message: Message, bot: Bot, command: str) -> bool:
    if not message.from_user:
        return False

    try:
        is_subscribed = await is_user_subscribed(bot, message.from_user.id)
    except SubscriptionCheckError:
        await message.answer(
            SUBSCRIPTION_CHECK_FAILED_TEXT,
            reply_markup=with_start_button(),
        )
        return False

    if is_subscribed:
        return True

    await message.answer(
        SUBSCRIPTION_REQUIRED_TEXT,
        reply_markup=with_start_button(get_subscription_keyboard(command)),
    )
    return False
