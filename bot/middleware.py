from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.user_storage import touch_user


class DatabaseMiddleware(BaseMiddleware):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self.session_factory() as session:
            data["db_session"] = session
            telegram_user = data.get("event_from_user")

            if telegram_user and not telegram_user.is_bot:
                await touch_user(session, telegram_user)

            try:
                result = await handler(event, data)
            except Exception:
                await session.rollback()
                raise

            await session.commit()
            return result
