from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot.keyboards.navigation import get_start_keyboard
from bot.services.cleanup_service import answer_and_track, cleanup_messages
from bot.constants import START_GUIDE_TEXT


router = Router()


async def send_start_screen(
    message,
    state: FSMContext,
    notice: str | None = None,
) -> None:
    text = START_GUIDE_TEXT if not notice else f"{notice}\n\n{START_GUIDE_TEXT}"
    await answer_and_track(
        message,
        state,
        text,
        reply_markup=get_start_keyboard(),
    )


@router.callback_query(F.data == "navigation:start")
async def go_to_start(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()

    if not callback.message:
        await state.clear()
        return

    chat_id = callback.message.chat.id
    message_id = callback.message.message_id

    await cleanup_messages(bot, state, chat_id)

    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except TelegramAPIError:
        pass

    await state.clear()
    await send_start_screen(callback.message, state)
