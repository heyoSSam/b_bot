from aiogram.types import User as TelegramUser
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from bot.constants import DEFAULT_NAME_STYLE
from bot.db.models import User


def get_telegram_tag(telegram_user: TelegramUser) -> str | None:
    if telegram_user.username:
        return f"@{telegram_user.username}"

    return None


async def touch_user(session: AsyncSession, telegram_user: TelegramUser) -> None:
    statement = (
        insert(User)
        .values(
            telegram_id=telegram_user.id,
            telegram_tag=get_telegram_tag(telegram_user),
            name_style=DEFAULT_NAME_STYLE,
        )
        .on_conflict_do_update(
            index_elements=[User.telegram_id],
            set_={
                "telegram_tag": get_telegram_tag(telegram_user),
                "updated_at": func.now(),
            },
        )
    )
    await session.execute(statement)


async def get_user(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def set_user_channel(
    session: AsyncSession,
    telegram_user: TelegramUser,
    channel_url: str,
) -> None:
    statement = (
        insert(User)
        .values(
            telegram_id=telegram_user.id,
            telegram_tag=get_telegram_tag(telegram_user),
            telegram_channel_url=channel_url,
            name_style=DEFAULT_NAME_STYLE,
        )
        .on_conflict_do_update(
            index_elements=[User.telegram_id],
            set_={
                "telegram_tag": get_telegram_tag(telegram_user),
                "telegram_channel_url": channel_url,
                "updated_at": func.now(),
            },
        )
    )
    await session.execute(statement)


async def set_user_name_style(
    session: AsyncSession,
    telegram_user: TelegramUser,
    name_style: str,
) -> None:
    statement = (
        insert(User)
        .values(
            telegram_id=telegram_user.id,
            telegram_tag=get_telegram_tag(telegram_user),
            name_style=name_style,
        )
        .on_conflict_do_update(
            index_elements=[User.telegram_id],
            set_={
                "telegram_tag": get_telegram_tag(telegram_user),
                "name_style": name_style,
                "updated_at": func.now(),
            },
        )
    )
    await session.execute(statement)
