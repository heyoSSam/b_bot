from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import Message


async def add_cleanup_message(state: FSMContext, message: Message | None) -> None:
    if not message:
        return

    data = await state.get_data()
    message_ids = list(data.get("cleanup_message_ids", []))
    message_id = getattr(message, "message_id", None)

    if message_id and message_id not in message_ids:
        message_ids.append(message_id)
        await state.update_data(cleanup_message_ids=message_ids)


async def answer_and_track(message: Message, state: FSMContext, *args: Any, **kwargs: Any) -> Message:
    sent_message = await message.answer(*args, **kwargs)
    await add_cleanup_message(state, sent_message)
    return sent_message


async def cleanup_messages(bot: Bot, state: FSMContext, chat_id: int) -> None:
    data = await state.get_data()
    message_ids = list(dict.fromkeys(data.get("cleanup_message_ids", [])))
    delete_messages = getattr(bot, "delete_messages", None)

    if delete_messages:
        try:
            for start_index in range(0, len(message_ids), 100):
                await delete_messages(
                    chat_id=chat_id,
                    message_ids=message_ids[start_index : start_index + 100],
                )
        except TelegramAPIError:
            pass
        else:
            await state.update_data(cleanup_message_ids=[])
            return

    for message_id in message_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except TelegramAPIError:
            continue

    await state.update_data(cleanup_message_ids=[])
