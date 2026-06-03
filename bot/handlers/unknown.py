import logging

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message


logger = logging.getLogger(__name__)
router = Router()
KNOWN_COMMANDS = {"/start", "/beat", "/beatpack", "/set_channel", "/set_style"}


def is_unknown_command(message: Message) -> bool:
    if not message.text or not message.text.startswith("/"):
        return False

    command = message.text.split()[0].split("@")[0]
    return command not in KNOWN_COMMANDS


@router.message(is_unknown_command)
async def handle_unknown_command(message: Message, state: FSMContext):
    await state.clear()
    logger.warning(f"User {message.from_user.id} sent an unknown command: {message.text}")
    await message.answer("Неизвестная команда. Используйте /start для списка доступных команд.")
