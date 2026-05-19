import asyncio 
import os 
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, Message
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from dotenv import load_dotenv

load_dotenv()

from bot.beat import router as beat_router
from bot.beatpack import router as beatpack_router
from bot.constants import START_GUIDE_TEXT
from bot.database import async_session, close_db, init_db
from bot.middleware import DatabaseMiddleware
from bot.navigation import router as navigation_router
from bot.settings import router as settings_router
from bot.unknown import router as unknown_router

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("TOKEN")

dp = Dispatcher()

bot = Bot(token=TOKEN)
dp.update.middleware(DatabaseMiddleware(async_session))
dp.include_router(beat_router)
dp.include_router(beatpack_router)
dp.include_router(settings_router)
dp.include_router(navigation_router)
dp.include_router(unknown_router)

@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    logger.info(f"User {message.from_user.id} started the bot.")
    await state.clear()
    await message.answer(START_GUIDE_TEXT)

async def main():
    logger.info("Starting bot...")
    await init_db()
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Показать команды"),
            BotCommand(command="beat", description="Собрать один бит"),
            BotCommand(command="beatpack", description="Собрать битпак"),
            BotCommand(command="set_channel", description="Сохранить канал"),
            BotCommand(command="set_style", description="Настроить шаблон подписи"),
        ]
    )
    try:
        await dp.start_polling(bot)
    finally:
        await close_db()

if __name__ == "__main__":
    asyncio.run(main())
