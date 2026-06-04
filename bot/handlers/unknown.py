import logging

from aiogram import Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.services.cleanup_service import add_cleanup_message, answer_and_track, cleanup_messages


logger = logging.getLogger(__name__)
router = Router()
KNOWN_COMMANDS = {"/start", "/beat", "/beatpack", "/set_channel", "/set_style"}


def is_unknown_command(message: Message) -> bool:
    if not message.text or not message.text.startswith("/"):
        return False

    command = message.text.split()[0].split("@")[0]
    return command not in KNOWN_COMMANDS


@router.message(is_unknown_command)
async def handle_unknown_command(message: Message, state: FSMContext, bot: Bot):
    await cleanup_messages(bot, state, message.chat.id)
    await state.clear()
    await add_cleanup_message(state, message)
    logger.warning(f"User {message.from_user.id} sent an unknown command: {message.text}")
    await answer_and_track(
        message,
        state,
        "Неизвестная команда. Используйте /start для списка доступных команд.",
    )
